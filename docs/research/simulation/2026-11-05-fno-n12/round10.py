"""Calendar sensitivity with a pre-decision official BSE closing-OI screen."""
from collections import Counter
import copy
import csv
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import json
import os
import subprocess

import round9 as run
from round9_strict import StrictReplay, verify as verify_strict
from round9_data import relative
from config import settings
from fno_exit_experiment import verify_archive_event
from intraday_spread_archive_adapter import read_archived_quote_events

IST = timezone(timedelta(hours=5, minutes=30))


@lru_cache(maxsize=1)
def catalogue():
    return json.loads((run.LOCAL / "catalogue.json").read_bytes())


@lru_cache(maxsize=128)
def prior_open_interest(day):
    previous = catalogue()[day]["previous"]
    data = {}
    with (run.LOCAL / relative("BSE", previous)).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["Product Code"].strip() != "BSXOPT":
                continue
            expiry = datetime.strptime(row["Expiry Date"].strip(), "%d %b %Y").date().isoformat()
            if expiry != catalogue()[day]["option_expiry"]:
                continue
            key = expiry, float(row["Strike Price"]), row["Option Type (Call/Put)"].strip()
            oi = int(float(row["Open Interest"]))
            assert oi >= 0 and oi % 20 == 0
            assert key not in data or data[key] == oi, key
            data[key] = oi
    return data


class PriorOI(run.SensexData):
    def observations(self, day):
        observations, excluded = super().observations(day)
        lookup = prior_open_interest(day)
        repaired = []
        for obs in observations:
            quotes = {}
            for token, quote in obs.options.items():
                c = quote.contract
                prior = lookup.get((c.expiry.isoformat(), c.strike, c.instrument_type), 0)
                if quote.oi == 0 and prior >= 2 * int(settings.FNO_MIN_OI):
                    quote = replace(quote, oi=prior)
                quotes[token] = quote
            repaired.append(replace(obs, options=quotes))
        return repaired, excluded


def verify():
    path = run.HERE / "round10-freeze.json"
    frozen = json.loads(path.read_bytes())
    assert frozen == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{path.relative_to(run.r.ROOT).as_posix()}"], cwd=run.r.ROOT))
    for file, sha in frozen["files"].items():
        assert run.digest(run.HERE / file) == sha, file
    verify_strict()


def eligible(sensex):
    return {d for d, v in sensex.manifest["coverage"].items()
            if v["status"] == "OBSERVED" and not v["future_missing"]}


def audit(sensex):
    from cross_index_coverage import ARCHIVE
    manifest = json.loads((ARCHIVE / "manifest.json").read_bytes())
    days = sorted(eligible(sensex) & set(manifest["quote_days"]) - set(manifest["unsealed_days"]))
    report = {}
    hashes = {}
    for day in days:
        target = sensex.manifest["day_contracts"][day]["option"]
        prior = prior_open_interest(day)
        counts, seen = Counter(), set()
        for name, expected in manifest["files_sha256"].items():
            if name.startswith(f"quotes/{day}/"):
                observed = run.digest(ARCHIVE / name)
                assert observed == expected, name
                hashes[name] = observed
        for event in read_archived_quote_events(ARCHIVE, days=[day]):
            c = event["contract"]
            if c.get("underlying") != "SENSEX" or c.get("expiry") != target or c.get("instrument_type") not in ("CE", "PE"):
                continue
            key = (event["received_at_utc"], c["instrument_token"])
            if key in seen:
                continue
            seen.add(key)
            quote, reason = verify_archive_event(event, token=int(c["instrument_token"]),
                                                 symbol=c["tradingsymbol"], max_age_seconds=10)
            if quote is None or not quote.bid or not quote.ask or quote.ask <= quote.bid:
                counts[f"unusable:{reason or 'prices'}"] += 1
                continue
            local = quote.receipt_at.astimezone(IST)
            if not 585 <= local.hour * 60 + local.minute < 885:
                continue
            raw = event["raw_packet"]
            size = min(int(raw["depth"][side][0]["quantity"]) for side in ("buy", "sell"))
            current = int(raw.get("oi") or 0)
            if size < int(c["lot_size"]) or current <= 0:
                counts["no_verified_oi_or_depth"] += 1
                continue
            assert int(event["oi"]) == current
            lag = prior.get((target, float(c["strike"]), c["instrument_type"]), 0)
            live_pass = current >= int(settings.FNO_MIN_OI)
            prior_pass = lag >= 2 * int(settings.FNO_MIN_OI)
            counts[f"prior_{int(prior_pass)}_current_{int(live_pass)}"] += 1
        report[day] = dict(counts)
    with (run.HERE / "round10-oi-audit.json").open("x", encoding="utf-8") as handle:
        json.dump({"days": report, "archive_file_hashes": hashes,
                   "archive_manifest_hash": run.digest(ARCHIVE / "manifest.json")}, handle, indent=2)
        handle.write("\n")
    print("OI audit", len(days), {k: sum(row.get(k, 0) for row in report.values())
                                  for k in sorted(set().union(*(set(x) for x in report.values())))}, flush=True)


def main():
    verify()
    stress = os.environ.get("N12_STRESS") == "1"
    tag = "stress" if stress else "base"
    sensex = PriorOI(stress)
    if len(os.sys.argv) == 2 and os.sys.argv[1] == "audit":
        audit(sensex)
        return
    year = run.r.YEAR
    run.r.f.Z.N.B.L._init()
    nifty = run.Y.dataset("year")
    allow = {d for d in eligible(sensex) if d.startswith(year)}
    calendar, _ = nifty.option_expiries()
    assert all(date.fromisoformat(d) in calendar for d in allow)
    original = json.loads((run.LOCAL / f"results-{year}-{tag}.json").read_bytes())
    controls = {k: original[k] for k in ("N11", "N11T")}
    for name, result in controls.items():
        if not stress:
            _, expected = run.trades(year, name)
            assert run.r.money(result) == run.r.money(expected)
    candidate = copy.deepcopy(run.r.books()["N11T"])
    candidate["label"] = f"N12|CALENDAR_PRIOR_OI|{tag}"
    if stress:
        candidate["cost"] = [400.0, 10.0]
    data = run.SharedDays(nifty, sensex, allow)
    run.Replay = StrictReplay
    result = run.evaluate(candidate, data)
    bfo_rows = [t for t in result["trades"] if t["tradingsymbol"].startswith("SENSEX")]
    for row in bfo_rows:
        if row["status"] != "CLOSED":
            continue
        assert row["entry_time"][:10] in allow
        assert row["entry_qty"] == 20 and not row.get("n10_children")
        gross = (row["exit_premium"] - row["entry_premium"]) * 20
        fee = run.FEES(row["entry_premium"], row["exit_premium"], 20, "BFO")
        assert abs(gross - fee - row["extra_cost"] - row["net_pnl"]) < .02
    with (run.LOCAL / f"prior-oi-results-{year}-{tag}.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, default=str)
    summary = {k: run.r.metrics(v) for k, v in {**controls, "CALENDAR_PRIOR_OI": result}.items()}
    summary["selected_days"] = sorted(data.selected)
    summary["sensex_trades"] = bfo_rows
    with (run.HERE / f"round10-{year}-{tag}.json").open("x", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    print(year, tag, "BFO", len(bfo_rows), "shared net", summary["CALENDAR_PRIOR_OI"]["net"],
          "unresolved", summary["CALENDAR_PRIOR_OI"]["unresolved"], flush=True)


if __name__ == "__main__":
    main()
