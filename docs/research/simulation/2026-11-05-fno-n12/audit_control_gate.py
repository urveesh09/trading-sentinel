"""Audit the causal gate against stored Production decisions on November 2–6."""

import argparse
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys


DAY_FIRST, DAY_LAST = "2026-11-02", "2026-11-06"
START, END = DAY_FIRST + "T09:15:00+05:30", DAY_LAST + "T15:50:00+05:30"
IDS = (55, 56, 57, 58, 59)


def capture() -> dict:
    from config import settings

    with closing(sqlite3.connect("file:/data/cache.db?mode=ro", uri=True, timeout=3)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")

        def rows(sql, args=()):
            return [dict(row) for row in db.execute(sql, args)]

        data = {
            "volatility": rows("SELECT session_date,recorded_at,atr_pct,usual,vol_up,above_line FROM fno_n11_gate "
                               "WHERE session_date BETWEEN ? AND ? ORDER BY session_date", (DAY_FIRST, DAY_LAST)),
            "closes": rows("SELECT id,exit_time,source,net FROM fno_n11_paper WHERE status='CLOSED' AND net IS NOT NULL "
                           "AND exit_time<? ORDER BY exit_time,id", (END,)),
            "shadow_entries": rows("SELECT id,entry_time,vol_lots,stood_aside FROM fno_n11_paper "
                                   "WHERE source='N11_PAPER' AND substr(entry_time,1,10) BETWEEN ? AND ? ORDER BY id",
                                   (DAY_FIRST, DAY_LAST)),
            "observed_entries": rows("SELECT id,entry_time FROM fno_positions WHERE source='FNO_PAPER' "
                                     "AND id BETWEEN ? AND ? ORDER BY id", (IDS[0], IDS[-1])),
        }
    return {**data, "release_sha": os.getenv("SENTINEL_RELEASE_SHA"),
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "need": settings.FNO_N11_STAND_NEED, "stand_ratio": settings.FNO_N11_STAND_RATIO}


def audit(raw: bytes) -> dict:
    root = Path(__file__).resolve().parents[4]
    sys.path.insert(0, str(root / "python-engine"))
    from control_gate import GateTape, ShadowClose, VolatilityReading

    data = json.loads(raw)
    stamp = datetime.fromisoformat
    readings = [VolatilityReading(stamp(row["recorded_at"]), row["atr_pct"], row["usual"])
                for row in data["volatility"]]
    closes = [ShadowClose(row["id"], stamp(row["exit_time"]), row["net"]) for row in data["closes"]]

    def tape(history):
        return GateTape(stamp(START), stamp(END), readings, history,
                        need=data["need"], stand_ratio=data["stand_ratio"])

    native = tape(closes)
    without_seeds = tape([close for close, row in zip(closes, data["closes"], strict=True)
                          if row["source"] != "research_seed"])
    for row in data["volatility"]:
        state = native.at(stamp(row["recorded_at"]))
        if (state.vol_up, state.above_line) != (bool(row["vol_up"]), bool(row["above_line"])):
            raise ValueError("volatility record differs")
    shadow_checks = []
    for row in data["shadow_entries"]:
        state = native.at(stamp(row["entry_time"]))
        if (state.vol_up, state.stand_aside) != (row["vol_lots"] == 2, bool(row["stood_aside"])):
            raise ValueError(f"shadow entry gate differs: {row['id']}")
        shadow_checks.append(row["id"])

    if tuple(row["id"] for row in data["observed_entries"]) != IDS:
        raise ValueError("observed entry scope differs")
    previous = json.loads(Path(__file__).with_name("deployed-risk-audit.json").read_bytes())
    historical = previous["positions"]
    entries = []
    for row, expected in zip(data["observed_entries"], historical, strict=True):
        at = stamp(row["entry_time"])
        state = native.at(at)
        prior = without_seeds.at(at)
        if (row["id"] != expected["id"] or round(state.paper_sum, 2) != expected["prior_20_net"]
                or not state.vol_up or state.stand_aside):
            raise ValueError(f"previous audit gate differs: {row['id']}")
        entries.append({"id": row["id"], **asdict(state), "paper_positive_without_seeds": prior.paper_positive,
                        "paper_count_without_seeds": prior.paper_count})

    coverage_file = Path(__file__).with_name("control-signal-coverage.json")
    historical_days = set(json.loads(coverage_file.read_bytes())["days"])
    recorded_days = {row["session_date"] for row in data["volatility"]}
    return {
        "historical_market_days": len(historical_days),
        "historical_days_with_observed_volatility": len(historical_days & recorded_days),
        "scope_start": START, "scope_end": END, "production_release": data["release_sha"],
        "evidence_sha256": hashlib.sha256(raw).hexdigest(), "need": data["need"],
        "stand_ratio": data["stand_ratio"], "observed_volatility_dates": len(data["volatility"]),
        "seed_closes": sum(row["source"] == "research_seed" for row in data["closes"]),
        "native_closes": sum(row["source"] == "N11_PAPER" for row in data["closes"]),
        "matched_shadow_entry_ids": shadow_checks, "observed_entries": entries,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", action="store_true")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if not args.runtime and args.evidence is None:
        parser.error("archive mode needs the scoped Production evidence")
    out = capture() if args.runtime else audit(args.evidence.read_bytes())
    print(json.dumps(out, sort_keys=True, indent=2, default=lambda at: at.isoformat()))
