"""Join frozen native N11 signal clocks to actual recorder quote availability."""

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, datetime, time, timedelta
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3

import pandas as pd

import control_quote_coverage as quotes
from deployed_entry_audit import HERE, IST, bars, digest, verify_sources
import fno_book
from fno_chain import select_strike_by_delta
from fno_engine_mom import evaluate_fno_mom
from fno_models import OptionType


DAILY = HERE.parent / "2026-10-31-fno-complements/_local/daily-2026.json"
START, FLAT = 9 * 60 + 30, quotes.FLAT
CONTROL = HERE / "control-quote-coverage.json"
SAMPLE_GAP = 90
NATIVE_MANAGE_GAP = 10


def clock(day, minute, second=0):
    return datetime.combine(day, time(minute // 60, minute % 60, second), IST)


def daily_gate(daily, day):
    cutoff = day - timedelta(days=fno_book.ADX_HISTORY_CALENDAR_DAYS)
    frame = daily.loc[pd.Timestamp(cutoff):pd.Timestamp(day)]
    adx, last_bar = fno_book.daily_adx(frame, day)
    return {"adx": adx, "side": fno_book.adx_side(adx),
            "prior_day": last_bar.isoformat() if last_bar else None}


def front_name(master):
    name, = (row[0] for row in master["contracts"].values() if row[3] == "FUT")
    return name


def prior_regimes(db, day):
    results = {}
    for ts, regime in db.execute(
        "SELECT evaluated_at,regime FROM fno_signals WHERE underlying='NIFTY' AND regime IS NOT NULL "
        "AND bar_ts>=? AND bar_ts<? ORDER BY evaluated_at",
        (day.isoformat(), (day + timedelta(days=1)).isoformat()),
    ):
        when = quotes.stamp(ts)
        if when.date() != day:
            continue
        if when in results and results[when] != regime:
            raise ValueError(f"Conflicting historical regime at {when}")
        results[when] = regime
    clocks = sorted(results)
    return clocks, [results[at] for at in clocks]


def source_coverage(frame, day, calendar):
    start = day - timedelta(days=21)
    history = {value for value in calendar if start <= value < day}
    observed = defaultdict(set)
    for at in frame.index:
        observed[at.date()].add(at.hour * 60 + at.minute)
    prior = set(range(9 * 60 + 15, 15 * 60 + 30, 5))
    current = set(range(9 * 60 + 15, quotes.CLOCKS[-1], 5))
    return {
        "missing_prior_sessions": [value.isoformat() for value in sorted(history) if not prior <= observed[value]],
        "missing_session_bar_minutes": sorted(current - observed[day]),
    }


def native_signals(day, name, own, volume, side, regimes):
    fno_book._RETEST.clear()
    frame = fno_book.with_participation(own, volume)
    clocks, labels = regimes
    fired = []
    missing_regime = []
    unknown_state_until = START
    for slot in range(START, quotes.CLOCKS[-1] + 1, 5):
        now = clock(day, slot, 1)
        i = bisect_right(clocks, now) - 1
        if i < 0:
            if slot in quotes.CLOCKS:
                missing_regime.append(slot)
            unknown_state_until = slot + 15
            fno_book._RETEST.clear()
            continue
        regime = labels[i]
        shipped = (evaluate_fno_mom(own, regime, now) if volume is None else
                   evaluate_fno_mom(own, regime, now, rvol_bars=volume))
        sig = fno_book.n11_signal(frame, regime, now, shipped=shipped, adx_side=side, underlying=name)
        if slot in quotes.CLOCKS and sig.direction:
            fired.append({"at": now.isoformat(), "minute": slot, "bar": sig.bar_ts,
                          "strategy": sig.strategy, "direction": sig.direction.value, "regime": regime,
                          "retest_context_complete": slot > unknown_state_until})
    return fired, missing_regime


def first_entry(row, name, master, batches):
    start = quotes.stamp(row["at"])
    choices = sorted((at, data) for (venue, at), data in batches.items()
                     if venue == name and start <= at < clock(start.date(), row["minute"] + 1))
    if not choices:
        return {"status": "no_sample_after_signal"}
    at, observed = choices[0]
    snapshot, complete = quotes.ladder_snapshot(name, at, master, observed)
    if snapshot is None or not complete:
        return {"status": "incomplete_verified_ladder", "receipt": at.isoformat()}
    picked = select_strike_by_delta(snapshot, OptionType.CE if row["direction"] == "LONG" else OptionType.PE, at)
    candidate = picked[0] if picked else None
    reject = quotes.entry_liquidity(candidate, at, lots=1)
    if reject:
        return {"status": reject, "receipt": at.isoformat()}
    two = quotes.entry_liquidity(candidate, at, lots=2) is None
    return {"status": "usable", "receipt": at.isoformat(), "symbol": candidate.contract.tradingsymbol,
            "option_token": candidate.contract.token, "front_token": snapshot.fut_quote.contract.token,
            "max_supported_lots": 2 if two else 1}


def collect_held(folder, files, day, masters, selected):
    expected = defaultdict(set)
    earliest = {}
    for name, rows in selected.items():
        for row in rows:
            when = quotes.stamp(row["receipt"])
            for token in (row["option_token"], row["front_token"]):
                expected[name].add(token)
                key = name, token
                earliest[key] = min(when, earliest.get(key, when))
    path, = [folder / name for name in files if name.startswith(f"quotes/{day}/") and name.endswith(".gz")]
    result = defaultdict(dict)
    seen = {}
    if not earliest:
        return result
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            event = json.loads(line)
            name = event["contract"]["underlying"]
            token = int(event["contract"]["instrument_token"])
            if token not in expected.get(name, ()):
                continue
            at = quotes.stamp(event["received_at_utc"])
            if at < earliest[name, token] or quotes.minute(at) > FLAT:
                continue
            key = name, token, at
            if key in seen:
                if seen[key] != event["raw_sha256"]:
                    raise ValueError(f"Conflicting held observation {key}")
                continue
            seen[key] = event["raw_sha256"]
            contract = quotes.exact_contract(event, name, masters[name])
            quote = quotes.quote_from_raw(event, contract)
            if quote is not None:
                result[name, token][at] = quote
    return result


def summarize_held(name, entry, packets, lots):
    start = quotes.stamp(entry["receipt"])
    end = clock(start.date(), FLAT)
    options = packets.get((name, entry["option_token"]), {})
    futures = packets.get((name, entry["front_token"]), {})
    usable = sorted(at for at in options.keys() & futures.keys()
                    if at >= start and futures[at].ltp > 0 and options[at].bid > 0 and
                    options[at].bid_quantity >= lots * options[at].contract.lot_size)
    through = [at for at in usable if at < end + timedelta(minutes=1)]
    flat = any(end <= at for at in through)
    last = through[-1] if flat else end
    stamps = [start, *through, last]
    maximum = max((b - a).total_seconds() for a, b in zip(stamps, stamps[1:]))
    return {"observations": len(through), "flat_bid": flat, "max_gap_sec": round(maximum, 6),
            "sampled_90sec_path": flat and maximum <= SAMPLE_GAP,
            "native_10sec_path": flat and maximum <= NATIVE_MANAGE_GAP}


def day_signals(db, day, master, daily, calendar):
    gate = daily_gate(daily, day)
    regimes = prior_regimes(db, day)
    frames = {name: bars(db, front_name(row), clock(day, quotes.CLOCKS[-1], 1)) for name, row in master.items()}
    available = {name: source_coverage(frame, day, calendar) for name, frame in frames.items()}
    result = {}
    for name, row in master.items():
        own_expiry = row["option_expiry"] == day.isoformat()
        borrowed = frames["NIFTY"] if name == "SENSEX" else None
        missing = available[name]
        thin = any(missing.values()) or (borrowed is not None and any(available["NIFTY"].values()))
        signals, missing_regime = ([], []) if own_expiry or gate["side"] is None else native_signals(
            day, name, frames[name], borrowed, gate["side"], regimes
        )
        result[name] = {**missing, "own_expiry": own_expiry, "truncated_input": thin,
                        "missing_regime_minutes": missing_regime, "signals": signals}
    return gate, result


def signal_inputs_hash(db, masters, days):
    """Fingerprint the archived rows this study can see, independent of daily export rotation."""
    first, last = (date.fromisoformat(days[0]) - timedelta(days=21)).isoformat(), days[-1] + "z"
    symbols = sorted({front_name(master) for venue in masters.values() for master in venue.values()})
    args = ",".join("?" for _ in symbols)
    frames = db.execute(
        f"SELECT tradingsymbol,datetime,open,high,low,close,volume FROM fut_candles WHERE interval='5minute' "
        f"AND tradingsymbol IN ({args}) AND datetime>=? AND datetime<? ORDER BY tradingsymbol,datetime",
        (*symbols, first, last),
    )
    hasher = hashlib.sha256()
    for row in frames:
        hasher.update(json.dumps(row, separators=(",", ":")).encode() + b"\n")
    hasher.update(b"regimes\n")
    regimes = db.execute(
        "SELECT evaluated_at,regime FROM fno_signals WHERE underlying='NIFTY' AND regime IS NOT NULL "
        "AND bar_ts>=? AND bar_ts<? ORDER BY bar_ts,evaluated_at,regime", (days[0], last)
    )
    for row in regimes:
        hasher.update(json.dumps(row, separators=(",", ":")).encode() + b"\n")
    return hasher.hexdigest()


def audit(folder, masters_path):
    source_hashes = verify_sources()
    control = json.loads(CONTROL.read_bytes())
    manifest = json.loads((folder / "manifest.json").read_bytes())
    db_path = folder / "fno-replay.sqlite"
    files = control["quote_segment_sha256"]
    if any(manifest["files_sha256"].get(name) != expected for name, expected in files.items()):
        raise ValueError("Recorder files no longer match the clock coverage audit")
    if digest(db_path) != manifest["files_sha256"]["fno-replay.sqlite"] or digest(masters_path) != control["source_sha256"]["masters"]:
        raise ValueError("Changed futures export or dated master archive")
    with gzip.open(masters_path, "rt", encoding="utf-8") as stream:
        masters = json.load(stream)
    daily = pd.DataFrame(json.loads(DAILY.read_bytes())["rows"], columns=["date", "open", "high", "low", "close"])
    daily.index = pd.to_datetime(daily.pop("date"))
    calendar = set(daily.index.date)
    out = {}
    with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        scoped_hash = signal_inputs_hash(db, masters, sorted(control["days"]))
        for day in sorted(control["days"]):
            master = {name: series[day] for name, series in masters.items()}
            gate, venues = day_signals(db, date.fromisoformat(day), master, daily, calendar)
            slots = {name: {row["minute"] for row in rows["signals"]} for name, rows in venues.items()}
            batches, _ = quotes.exact_batches(folder, files, day, master, slots) if any(slots.values()) else ({}, {})
            selected = defaultdict(list)
            for name, rows in venues.items():
                for row in rows["signals"]:
                    row["entry_evidence"] = first_entry(row, name, master[name], batches)
                    if row["entry_evidence"]["status"] == "usable":
                        selected[name].append(row["entry_evidence"])
            packets = collect_held(folder, files, day, master, selected)
            for name, entries in selected.items():
                for entry in entries:
                    entry["held_1lot"] = summarize_held(name, entry, packets, 1)
                    if entry["max_supported_lots"] == 2:
                        entry["held_2lot"] = summarize_held(name, entry, packets, 2)
            out[day] = {"prior_adx_gate": gate, "venues": venues}
            print(day, dict(Counter(row["entry_evidence"]["status"] for venue in venues.values()
                                    for row in venue["signals"])), flush=True)
    return {"source_sha256": {"control": digest(CONTROL), "daily": digest(DAILY), "scoped_signal_inputs": scoped_hash},
            "reference_sources_sha256": source_hashes,
            "criteria": {"sample_gap_sec": SAMPLE_GAP, "native_manage_gap_sec": NATIVE_MANAGE_GAP,
                         "signal_clock": "one second after the 5m close with last causal same-day regime"},
            "days": out}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("export", type=Path)
    args = parser.parse_args()
    result = audit(args.export, HERE / "_local/deployed-control-masters.json.gz")
    path = HERE / "control-signal-coverage.json"
    if path.is_file():
        if json.loads(path.read_bytes()) != result:
            raise ValueError("Recomputed signal coverage differs")
    else:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")


if __name__ == "__main__":
    main()
