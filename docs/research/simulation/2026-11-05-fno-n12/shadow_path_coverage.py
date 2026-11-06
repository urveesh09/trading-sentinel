"""Historical path evidence for individual native N11 one-lot shadows."""

import argparse
from collections import Counter
from contextlib import closing, redirect_stdout
from datetime import date, timedelta
import gzip
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pandas as pd

import control_quote_coverage as quotes
import control_signal_coverage as signals
from config import settings
from fno_book import exit_overrides
from fno_engine_mom import MomSignal
from fno_entry_plan import EntryState, plan_single_leg_entry
from fno_exit_rules import evaluate_single_leg_exit, live_single_leg_exit_params
from fno_models import FnoDirection
from fno_n11 import eff_clock


HERE = Path(__file__).resolve().parent
SAMPLE_INTERVAL_SEC = 55
MAX_GAP_SEC = 90
ALLOCATION = 250_000.0


def path(entry_at, position, strategy, lotsize, options, futures):
    """First fresh same-packet one-lot bid and futures mark at each check."""
    prior = entry_at
    largest_gap = 0.0
    looks = 0
    breach = None
    baseline = {**live_single_leg_exit_params(settings), **exit_overrides(strategy)}
    hard_flat_at = signals.clock(entry_at.date(), settings.FNO_HARD_FLAT_MIN)
    latest = hard_flat_at + timedelta(minutes=1)
    sign = 1 if position.direction == "LONG" else -1
    risk = abs(position.entry_underlying - position.stop_underlying)

    for at in sorted(options.keys() & futures.keys()):
        if not entry_at < at < latest:
            continue
        bid, future = options[at].bid, futures[at].ltp
        if bid <= 0 or future <= 0 or options[at].bid_quantity < lotsize:
            continue
        gap = (at - prior).total_seconds()
        hard_flat = at >= hard_flat_at
        if not hard_flat and gap < SAMPLE_INTERVAL_SEC:
            continue
        largest_gap = max(largest_gap, gap)
        if gap > MAX_GAP_SEC:
            return {"status": "held_gap", "last_verified": prior.isoformat(),
                    "next_usable": at.isoformat(), "gap_sec": round(gap, 6), "looks": looks}
        looks += 1
        params = dict(baseline)
        if strategy == "N11_EFF":
            params["FNO_TIME_STOP_MIN"] = eff_clock(
                (at - entry_at).total_seconds() / 60, position.trail_active, bid,
                position.entry_premium, lotsize, 1,
                sign * (future - position.entry_underlying) / risk if risk > 0 else 0.0,
            )
        result = evaluate_single_leg_exit(
            position, now_ist=at, fut_price=future, exit_px_basis=bid, hard_flat=hard_flat,
            params=params, lock_breach_since=breach,
        )
        if result.exit_reason:
            return {"status": "resolved_at_sampled_clock", "exit_reason": result.exit_reason,
                    "exit_at": at.isoformat(), "max_gap_sec": round(largest_gap, 6), "looks": looks}
        if result.persist_trail:
            position.trail_active = int(result.trail_active)
            position.trail_stop_underlying = result.trail_stop
            position.best_underlying = result.best_underlying
            position.best_premium = result.best_premium
        breach = result.lock_breach_since
        prior = at
    return {"status": "no_qualified_exit_or_flat_bid", "last_verified": prior.isoformat(), "looks": looks}


def entry_path(row, master, batches, packets):
    entry = row["entry_evidence"]
    if entry["status"] != "usable":
        return {"status": entry["status"]}
    at, batch = signals.first_entry_sample(row, "NIFTY", batches)
    chain, complete = quotes.ladder_snapshot("NIFTY", at, master, batch)
    if not complete:
        raise ValueError("qualified candidate lost its full ladder")
    sig = MomSignal(bar_ts=row["bar"], direction=FnoDirection(row["direction"]), strategy=row["strategy"],
                    **row["geometry"])
    initial = EntryState(pool=ALLOCATION, open_premium=0.0, open_positions=0, trades_today=0,
                         active_kill_switches=(), held_symbols=frozenset(), is_trading_day=True,
                         is_expiry_day=False, lot_ceiling=1)
    plan = plan_single_leg_entry(sig, chain, row["regime"], at, initial)
    if not plan.accepted:
        return {"status": "one_lot_planner_rejected", "reason": plan.reject_reason}
    quote = plan.quote
    if quote.contract.token != entry["option_token"] or plan.lots != 1:
        raise ValueError("native shadow entry differs from the frozen quote identity")
    position = SimpleNamespace(
        direction=sig.direction.value, entry_underlying=chain.forward,
        stop_underlying=sig.stop_underlying, target_underlying=sig.target_underlying,
        atr_at_entry=sig.atr, entry_premium=quote.ask,
        premium_stop=round((1 - settings.FNO_STOP_PREMIUM_PCT) * quote.ask, 2),
        entry_time=at.isoformat(), best_underlying=chain.forward, best_premium=None,
        trail_active=0, trail_stop_underlying=None,
    )
    return path(at, position, sig.strategy, plan.lot_size, packets.get(("NIFTY", entry["option_token"]), {}),
                packets.get(("NIFTY", entry["front_token"]), {}))


def audit(folder: Path, masters_path: Path) -> dict:
    manifest = json.loads((folder / "manifest.json").read_bytes())
    control = json.loads(signals.CONTROL.read_bytes())
    reference_file = HERE / "control-signal-coverage.json"
    reference = json.loads(reference_file.read_bytes())
    files = control["quote_segment_sha256"]
    db_path = folder / "fno-replay.sqlite"
    if any(manifest["files_sha256"].get(name) != expected for name, expected in files.items()):
        raise ValueError("export manifest differs from the frozen recorder scope")
    if (signals.digest(db_path) != manifest["files_sha256"]["fno-replay.sqlite"]
            or signals.digest(masters_path) != control["source_sha256"]["masters"]
            or signals.digest(signals.DAILY) != reference["source_sha256"]["daily"]
            or signals.verify_sources() != reference["reference_sources_sha256"]):
        raise ValueError("futures data, master, or native source changed")

    with gzip.open(masters_path, "rt", encoding="utf-8") as stream:
        masters = json.load(stream)
    daily = pd.DataFrame(json.loads(signals.DAILY.read_bytes())["rows"], columns=["date", "open", "high", "low", "close"])
    daily.index = pd.to_datetime(daily.pop("date"))
    calendar = set(daily.index.date)
    output = {}
    totals = Counter()
    with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        scope = sorted(reference["days"])
        if signals.signal_inputs_hash(db, masters, scope) != reference["source_sha256"]["scoped_signal_inputs"]:
            raise ValueError("scoped regime and futures inputs changed")
        for day in scope:
            dated = {name: series[day] for name, series in masters.items()}
            _, venues = signals.day_signals(db, date.fromisoformat(day), dated, daily, calendar,
                                            include_geometry=True)
            rows = venues["NIFTY"]["signals"]
            prior = reference["days"][day]["venues"]["NIFTY"]["signals"]
            if not rows and not prior:
                output[day] = []
                continue
            batches, _ = quotes.exact_batches(folder, files, day, dated, {"NIFTY": {row["minute"] for row in rows}})
            for row, old in zip(rows, prior, strict=True):
                comparable = {key: value for key, value in row.items() if key != "geometry"}
                frozen = {key: value for key, value in old.items() if key != "entry_evidence"}
                entry = signals.first_entry(row, "NIFTY", dated["NIFTY"], batches)
                expected = {key: value for key, value in old["entry_evidence"].items() if not key.startswith("held_")}
                if comparable != frozen or entry != expected:
                    raise ValueError(f"frozen signal or selected quote differs: {day}")
                row["entry_evidence"] = entry
            packets = signals.collect_held(
                folder, files, day, dated,
                {"NIFTY": [row["entry_evidence"] for row in rows if row["entry_evidence"]["status"] == "usable"]},
            )
            results = []
            for row, old in zip(rows, prior, strict=True):
                result = entry_path(row, dated["NIFTY"], batches, packets)
                result["signal_at"] = row["at"]
                result["strategy"] = row["strategy"]
                result["complete_signal_context"] = not venues["NIFTY"]["truncated_input"] and row["retest_context_complete"]
                result["prior_through_flat_90sec"] = old["entry_evidence"].get("held_1lot", {}).get("sampled_90sec_path", False)
                results.append(result)
                totals[result["status"]] += 1
            output[day] = results
    return {"scope": "independent NIFTY shadow paths, representative clocks, no portfolio cash result",
            "allocation": ALLOCATION, "pre_flat_minimum_interval_sec": SAMPLE_INTERVAL_SEC,
            "maximum_held_gap_sec": MAX_GAP_SEC, "signal_reference_sha256": signals.digest(reference_file),
            "counts": dict(sorted(totals.items())), "days": output}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("export", type=Path)
    parser.add_argument("--masters", type=Path, default=HERE / "_local/deployed-control-masters.json.gz")
    args = parser.parse_args()
    with redirect_stdout(sys.stderr):
        report = audit(args.export, args.masters)
    print(json.dumps(report, indent=2, sort_keys=True))
