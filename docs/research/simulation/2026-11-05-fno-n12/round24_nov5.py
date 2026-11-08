"""Check necessary mixed-rule conditions on the frozen November 5 observations."""

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3

import round24 as mix


HERE = Path(__file__).resolve().parent
DAY = "2026-11-05"
END = "2026-11-06"


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def necessary_exit_checks(row, held, bars):
    side = 1 if row["direction"] == "LONG" else -1
    entered = datetime.fromisoformat(row["entry_time"])
    signal = datetime.fromisoformat(row["bar_ts"])
    risk = abs(row["entry_underlying"] - row["stop_underlying"])
    high, low, _ = bars[signal]
    edge = (low if side == 1 else high) - side * .10 * risk
    counts = Counter()
    for mark in held:
        at = datetime.fromisoformat(mark["at"])
        if not 600 <= (at - entered).total_seconds() <= 2100:
            continue
        counts["age_eligible"] += 1
        # A full-lot fresh bid below entry is required. Assume freshness and
        # depth are sufficient for every positive recorded bid for this bound.
        if not 0 < (mark.get("bid") or 0.) < row["entry_premium"]:
            continue
        counts["below_entry_bid"] += 1
        if not 0 < side * (edge - row["stop_underlying"]) < risk:
            continue
        newest = at.replace(minute=at.minute // 5 * 5, second=0, microsecond=0, tzinfo=None) - timedelta(minutes=5)
        earlier = newest - timedelta(minutes=5)
        if signal >= earlier:
            continue
        if newest not in bars or earlier not in bars or not mark.get("fut"):
            counts["missing_required_observation"] += 1
            continue
        if all(side * (px - edge) < 0 for px in (bars[earlier][2], bars[newest][2], mark["fut"])):
            counts["possible_invalidation"] += 1
    return {"id": row["id"], "total_held_looks": len(held), "adverse_edge": edge,
            **{key: counts[key] for key in ("age_eligible", "below_entry_bid", "missing_required_observation",
                                           "possible_invalidation")}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("export", type=Path)
    args = parser.parse_args()
    folder = args.export
    manifest = json.loads((folder / "manifest.json").read_bytes())
    proof = json.loads((HERE / "round19-nov5-freeze.json").read_bytes())
    assert digest(folder / "manifest.json") == proof["export_manifest"]
    db_path = folder / "fno-replay.sqlite"
    held_path = folder / "fno_exit_paths" / f"{DAY}.jsonl"
    for path in (db_path, held_path):
        assert digest(path) == manifest["files_sha256"][path.relative_to(folder).as_posix()]
    day_forecast = json.loads((HERE / "round19-nov5-results.json").read_bytes())["forecast"]
    vol_forecasts = [day_forecast[f"{source}_log_forecast"] for source in ("realized_only", "implied")]
    assert day_forecast["day"] == DAY and mix.forecast_supports_invalidation(vol_forecasts)
    with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        rows = db.execute("SELECT * FROM fno_positions WHERE entry_date=? AND source='FNO_PAPER' "
                          "AND underlying='NIFTY' ORDER BY id", (DAY,)).fetchall()
        rejected = db.execute("SELECT reject_reason,count(*) FROM fno_signals WHERE evaluated_at>=? AND evaluated_at<? "
                              "AND underlying='NIFTY' AND leg='FNO_PAPER' AND accepted=0 GROUP BY 1", (DAY, END)).fetchall()
        bars = {datetime.fromisoformat(row[0]): tuple(row[1:]) for row in db.execute(
            "SELECT datetime,high,low,close FROM fut_candles WHERE tradingsymbol='NIFTY26NOVFUT' AND interval='5minute' "
            "AND datetime>=? AND datetime<?", (DAY, END))}
    assert len(rows) == 3 and bars
    held = defaultdict(list)
    with held_path.open(encoding="utf-8") as handle:
        for line in handle:
            mark = json.loads(line)
            if mark["source"] == "FNO_PAPER" and mark["underlying"] == "NIFTY":
                held[mark["position_id"]].append(mark)
    checked = [necessary_exit_checks(row, held[row["id"]], bars) for row in rows]
    assert all(row["age_eligible"] > 0 and not row["missing_required_observation"] for row in checked)
    result = {"day": DAY, "forecast": vol_forecasts, "forecast_supports_invalidation": True,
              "recorded_paper_refusals": dict(rejected), "eligible_logged_fallback_refusals": sum(
                  n for reason, n in rejected if reason in mix.fallback.REFUSALS), "held": checked,
              "observed_single_net": round(sum(row["pnl"] for row in rows), 2),
              "scope": "recorded FNO_PAPER refusals and necessary exit conditions on observed held paths",
              "export_manifest_sha256": proof["export_manifest"]}
    with (HERE / "round24-nov5.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
