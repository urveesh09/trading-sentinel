"""Measure SENSEX data overlap and quote spread without scoring a strategy."""
from collections import Counter, defaultdict
from datetime import timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

from anatomy import DATASETS, read

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OPS = Path.home() / "sentinel-operations"
DATA = OPS / "breeze-history-20261029/data/breeze-history.sqlite"
ARCHIVE = OPS / ("fno-forward-panel-20261028/docs/research/fno/2026-10-28-forward-panel/"
                 "_local/exports/20261105T103005Z")
sys.path.insert(0, str(ROOT / "python-engine"))
from fno_exit_experiment import verify_archive_event
from intraday_spread_archive_adapter import read_archived_quote_events

IST = timezone(timedelta(hours=5, minutes=30))
BINS = (50, 100, 150, 200, 300, 450, 700, 1000, float("inf"))


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def inventory():
    lower, upper = "2025-07-01", "2026-11-01"
    with sqlite3.connect(DATA.resolve().as_uri() + "?mode=ro", uri=True) as con:
        day_kinds = con.execute(
            """SELECT substr(datetime,1,10),kind,count(*) FROM candles WHERE
               underlying='SENSEX' AND interval='1minute' AND datetime>=? AND datetime<?
               AND kind IN ('index','future','option') GROUP BY 1,2 ORDER BY 1,2""",
            (lower, upper),
        ).fetchall()
        series = [r[0] for r in con.execute(
            """SELECT DISTINCT expiry FROM candles WHERE underlying='SENSEX' AND kind='option'
               AND interval='1minute' AND expiry>=? AND expiry<? ORDER BY expiry""",
            (lower, "2026-11-15"),
        )]
    counts = defaultdict(Counter)
    observed = defaultdict(set)
    for day, kind, rows in day_kinds:
        counts[day[:7]][f"{kind}_days"] += 1
        counts[day[:7]][f"{kind}_rows"] += rows
        if rows:
            observed[day].add(kind)
    nifty_manifests = [read(DATASETS[year] / "manifest.json") for year in ("2025", "2026")]
    nifty_dates = {d for m in nifty_manifests for d in m["sessions"]}
    nifty_expiries = {d for m in nifty_manifests for d in m["weekly_expiry_calendar"]}
    triple = {d for d, kinds in observed.items() if kinds == {"index", "future", "option"}}
    aligned = triple & nifty_dates
    possible_sleeve = aligned & nifty_expiries - set(series)
    return {
        "window": [lower, upper], "monthly": {month: dict(count) for month, count in counts.items()},
        "sensex_observed_series": series, "overlapping_presence_days": sorted(aligned),
        "potential_calendar_sleeve_days": sorted(possible_sleeve),
        "eligibility": "Presence audit only. Verify complete front contracts, exact clock and dated calendars.",
    }


def percentile(values, probability):
    ordered = sorted(values)
    index = min(len(ordered) - 1, int((len(ordered) - 1) * probability))
    return round(ordered[index], 4)


def spread_sample():
    manifest = read(ARCHIVE / "manifest.json")
    dates = sorted(d for d in manifest["quote_days"] if "2026-09-10" <= d <= "2026-10-28")[::4]
    levels, excludes, file_hashes = defaultdict(list), Counter(), {}
    for day in dates:
        prefix = f"quotes/{day}/"
        for name, expected in manifest["files_sha256"].items():
            if name.startswith(prefix):
                actual = digest(ARCHIVE / name)
                assert actual == expected, name
                file_hashes[name] = actual
        nearest = {u: next(e for e in exps if e >= day) for u, exps in manifest["option_expiries"].items()}
        seen = set()
        for event in read_archived_quote_events(ARCHIVE, days=[day]):
            c = event.get("contract", {})
            u = c.get("underlying")
            if u not in nearest or c.get("instrument_type") not in ("PE", "CE"):
                continue
            if c["expiry"] != nearest[u] or c["expiry"] == day:
                continue
            key = (event["received_at_utc"], c["instrument_token"])
            if key in seen:
                continue
            seen.add(key)
            q, reason = verify_archive_event(event, token=int(c["instrument_token"]),
                                             symbol=c["tradingsymbol"], max_age_seconds=10)
            if not q:
                excludes[f"{u}:{reason}"] += 1
                continue
            at = q.receipt_at.astimezone(IST)
            if not 585 <= at.hour * 60 + at.minute <= 910:
                continue
            if not q.bid or not q.ask or q.ask <= q.bid:
                excludes[f"{u}:invalid_depth_prices"] += 1
                continue
            raw = event["raw_packet"]["depth"]
            lots = [int(raw[side][0]["quantity"]) for side in ("buy", "sell")]
            if min(lots) < int(c["lot_size"]):
                excludes[f"{u}:insufficient_depth"] += 1
                continue
            mid = (q.bid + q.ask) / 2
            upper = next(x for x in BINS if mid < x)
            levels[(u, upper)].append((q.ask - q.bid, mid))
    stats = {}
    for (underlying, upper), values in sorted(levels.items()):
        spreads = [x[0] for x in values]
        stats[f"{underlying}:{upper}"] = {
            "count": len(spreads), "p50": percentile(spreads, .5), "p75": percentile(spreads, .75),
            "p90": percentile(spreads, .9),
            "over_cap_pct": round(100 * sum(spread / mid > .015 for spread, mid in values) / len(values), 2),
        }
    return {"sample_days": dates, "quotes_by_premium_bin": stats, "exclusions": dict(excludes),
            "manifest_sha256": digest(ARCHIVE / "manifest.json"), "files_sha256": file_hashes}


def main():
    output = {"history": inventory(), "spread": spread_sample()}
    with (HERE / "cross-index-coverage.json").open("x", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print("Overlapping dates", len(output["history"]["overlapping_presence_days"]),
          "potential sleeve dates", len(output["history"]["potential_calendar_sleeve_days"]),
          "spread bins", len(output["spread"]["quotes_by_premium_bin"]), flush=True)


if __name__ == "__main__":
    main()
