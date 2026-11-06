"""Check whether the frozen recorder tape can support the two-index control."""

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
import gzip
import hashlib
import json
from pathlib import Path

from deployed_entry_audit import HERE, IST, digest
from config import settings
from fno_chain import ChainSnapshot, select_strike_by_delta
from fno_exit_experiment import verify_archive_event
from fno_models import Contract, ContractQuote, OptionType
from research_quote_collector import _provider_timestamp


LAST = "2026-10-28"
VENUES = {"NIFTY": ("NFO", 50), "SENSEX": ("BFO", 100)}
CLOCKS = range(9 * 60 + 45, 14 * 60 + 45, 5)
FLAT = 15 * 60 + 10
MAX_SKEW = 10
LOTS = 2
POLICY = ("FNO_STRIKE_WINDOW", "FNO_TARGET_DELTA", "FNO_MIN_OI", "FNO_MIN_VOL",
          "FNO_MAX_SPREAD_PCT", "FNO_MAX_QUOTE_AGE_SEC")


def stamp(value):
    return datetime.fromisoformat(value).astimezone(IST)


def minute(receipt):
    return receipt.hour * 60 + receipt.minute


def exact_contract(event, name, master):
    token = str(event["contract"]["instrument_token"])
    row = master["contracts"].get(token)
    if row is None:
        return None
    record = event["contract"]
    expected = [record[key] for key in ("tradingsymbol", "expiry", "strike", "instrument_type", "lot_size", "tick_size")]
    if row != expected or record["exchange"] != VENUES[name][0]:
        raise ValueError(f"Recorder and dated master disagree for {name} {token}")
    symbol, expiry, strike, kind, lot, tick = row
    return Contract(int(token), symbol, name, date.fromisoformat(expiry), strike, kind, lot, tick)


def quote_from_raw(event, contract):
    verified, _ = verify_archive_event(event, token=contract.token, symbol=contract.tradingsymbol,
                                       max_age_seconds=MAX_SKEW)
    if verified is None:
        return None
    raw = event["raw_packet"]
    oi, volume = int(raw.get("oi") or 0), int(raw.get("volume") or 0)
    last_trade = _provider_timestamp(raw.get("last_trade_time"))[1]
    if (oi, volume, last_trade) != (event["oi"] or 0, event["volume"] or 0, event["last_trade_time"]):
        raise ValueError(f"Recorder liquidity differs from raw provider packet for {contract.token}")
    depth = {}
    for side, field in (("buy", "buy_depth"), ("sell", "sell_depth")):
        levels = raw.get("depth", {}).get(side) or ()
        observed = event[field] or ()
        quantity = int(levels[0]["quantity"] or 0) if levels else 0
        if quantity != (int(observed[0]["quantity"] or 0) if observed else 0):
            raise ValueError(f"Recorder depth differs from raw provider packet for {contract.token}")
        depth[side] = quantity
    return ContractQuote(contract=contract, bid=verified.bid or 0., ask=verified.ask or 0., ltp=verified.ltp or 0.,
                         oi=oi, volume=volume, last_trade_time=stamp(last_trade) if last_trade else None,
                         bid_quantity=depth["buy"], ask_quantity=depth["sell"])


def entry_liquidity(quote, at, lots=LOTS):
    if quote is None:
        return "no_selected_strike"
    age = (at - quote.last_trade_time).total_seconds() if quote.last_trade_time else float("inf")
    if not 0 <= age <= settings.FNO_MAX_QUOTE_AGE_SEC:
        return "last_trade_age"
    if quote.oi < settings.FNO_MIN_OI or quote.volume < settings.FNO_MIN_VOL:
        return "open_interest_or_volume"
    if not 0 < quote.bid < quote.ask or quote.spread_pct > settings.FNO_MAX_SPREAD_PCT:
        return "spread_or_missing_book"
    if min(quote.bid_quantity, quote.ask_quantity) < lots * quote.contract.lot_size:
        return "top_level_depth"
    return None


def ladder_snapshot(name, at, master, quotes):
    futures = [q for q in quotes.values() if q.contract.instrument_type == "FUT" and q.ltp > 0]
    if len(futures) != 1:
        return None, False
    future, = futures
    expiry = date.fromisoformat(master["option_expiry"])
    _, step = VENUES[name]
    atm = round(future.ltp / step) * step
    width = settings.FNO_STRIKE_WINDOW * step
    expected = {int(token) for token, row in master["contracts"].items()
                if row[3] in ("CE", "PE") and abs(row[2] - atm) <= width}
    options = {(q.contract.strike, q.contract.instrument_type): q for token, q in quotes.items() if token in expected}
    full = bool(expected) and expected.issubset(quotes)
    snapshot = ChainSnapshot(at, expiry, future.ltp, None, future.contract.lot_size, future, options)
    return snapshot, full


def batch_state(name, at, master, quotes):
    snapshot, full = ladder_snapshot(name, at, master, quotes)
    if snapshot is None:
        return "no_single_front_future", False, (), ()
    flat_bids = tuple(sorted(q.contract.token for q in snapshot.quotes.values()
                             if q.bid > 0 and q.bid_quantity >= LOTS * q.contract.lot_size))
    selected = []
    for right in (OptionType.CE, OptionType.PE):
        picked = select_strike_by_delta(snapshot, right, at)
        candidate = picked[0] if picked else None
        reason = entry_liquidity(candidate, at)
        if reason is not None:
            return f"{right.value}:{reason}", full, (), flat_bids
        selected.append(candidate.contract.token)
    return None, full, tuple(selected), flat_bids


def exact_batches(folder, hashes, day, master, slots=None):
    paths = [name for name in hashes if name.startswith(f"quotes/{day}/")]
    for name in paths:
        if digest(folder / name) != hashes[name]:
            raise ValueError(f"Changed recorder segment {name}")
    path, = [folder / name for name in paths if name.endswith(".gz")]
    groups = defaultdict(dict)
    rejected = Counter()
    seen = {}
    observed = {name: stamp(item["observed_at"]) for name, item in master.items()}
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            event = json.loads(line)
            if not str(event["mode"]).startswith("KITE_REST"):
                continue
            at = stamp(event["received_at_utc"])
            name = event["contract"]["underlying"]
            if name not in master or at < observed[name] or master[name]["option_expiry"] == day:
                continue
            slot = minute(at)
            wanted = slot in CLOCKS or slot == FLAT if slots is None else slot in slots.get(name, ())
            if not wanted:
                continue
            contract = exact_contract(event, name, master[name])
            if contract is None:
                continue
            key = name, at, contract.token
            if key in seen:
                if seen[key] != event["raw_sha256"]:
                    raise ValueError(f"Conflicting provider packet {key}")
                continue
            seen[key] = event["raw_sha256"]
            batch = groups[name, at]
            quote = quote_from_raw(event, contract)
            if quote is None:
                rejected[name] += 1
            else:
                batch[contract.token] = quote
    return groups, rejected


def jointly_available(left, right):
    return any(abs((a - b).total_seconds()) <= MAX_SKEW for a in left for b in right)


def one_day(day, master, batches, rejected):
    usable = defaultdict(list)
    complete = defaultdict(list)
    picked, flat = defaultdict(set), defaultdict(set)
    failures = defaultdict(Counter)
    totals = Counter()
    for (name, at), quotes in sorted(batches.items()):
        slot = minute(at)
        reason, full, tokens, bids = batch_state(name, at, master[name], quotes)
        if slot == FLAT:
            flat[name].update(bids)
            continue
        totals[name] += 1
        if reason:
            failures[name][reason] += 1
        else:
            usable[name, slot].append(at)
            picked[name].update(tokens)
            if full:
                complete[name, slot].append(at)
    venues = {}
    for name, item in master.items():
        venues[name] = {
            "nearest_expiry": item["option_expiry"], "front_expiry": item["front_expiry"],
            "own_expiry": item["option_expiry"] == day, "master_sha256": item["manifest_sha256"],
            "observed_entry_batches": totals[name], "unverified_provider_packets": rejected[name],
            "sampled_both_right_clocks": [slot for slot in CLOCKS if usable[name, slot]],
            "full_ladder_both_right_clocks": [slot for slot in CLOCKS if complete[name, slot]],
            "liquidity_failures": dict(failures[name]),
            "selected_tokens": len(picked[name]), "selected_tokens_with_flat_bid": len(picked[name] & flat[name]),
        }
    return {"venues": venues,
            "joint_sampled_clocks": [slot for slot in CLOCKS
                                      if jointly_available(usable["NIFTY", slot], usable["SENSEX", slot])],
            "joint_full_ladder_clocks": [slot for slot in CLOCKS
                                         if jointly_available(complete["NIFTY", slot], complete["SENSEX", slot])]}


def audit(folder, master_path):
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    with gzip.open(master_path, "rt", encoding="utf-8") as stream:
        masters = json.load(stream)
    days = [day for day in sorted(manifest["quote_days"]) if "2026-09-10" <= day <= LAST and day not in manifest["unsealed_days"]]
    if len(days) != 31 or any(set(series) != set(days) for series in masters.values()):
        raise ValueError("The quote and dated master calendars do not match the frozen 31 dates")
    segments = {name: value for name, value in manifest["files_sha256"].items()
                if name.startswith("quotes/") and name.split("/")[1] in days}
    result = {}
    for day in days:
        current = {name: series[day] for name, series in masters.items()}
        batches, rejected = exact_batches(folder, segments, day, current)
        result[day] = one_day(day, current, batches, rejected)
        print(day, len(result[day]["joint_full_ladder_clocks"]), "strict paired clocks", flush=True)
    scope = json.dumps(segments, sort_keys=True, separators=(",", ":")).encode()
    return {"source_sha256": {"quote_subset": hashlib.sha256(scope).hexdigest(), "masters": digest(master_path)},
            "quote_segment_sha256": segments,
            "criteria": {**{name: getattr(settings, name) for name in POLICY},
                         "required_top_level_lots": LOTS, "provider_age_and_cross_venue_skew_sec": MAX_SKEW,
                         "entry_clocks_ist_minutes": list(CLOCKS), "flat_clock_ist_minutes": FLAT},
            "days": result}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("export", type=Path)
    args = parser.parse_args()
    result = audit(args.export, HERE / "_local/deployed-control-masters.json.gz")
    output = HERE / "control-quote-coverage.json"
    if output.is_file():
        if json.loads(output.read_bytes()) != result:
            raise ValueError("Recomputed quote coverage differs")
    else:
        with output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")


if __name__ == "__main__":
    main()
