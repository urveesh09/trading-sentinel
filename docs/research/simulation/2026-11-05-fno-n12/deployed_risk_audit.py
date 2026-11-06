"""Recompute accepted-contract sizing and cash reservations for both venues."""

import argparse
from collections import Counter
from contextlib import closing
from datetime import date, datetime
import json
from pathlib import Path
import sqlite3

from deployed_control_nov5 import HERE, IDS, digest
from config import settings
from fno_adaptive_risk import Close, policy_from_settings, risk_stance
from fno_costs import calc_fno_costs, options_exchange_for
from fno_entry_plan import EntryPlan, EntryState
from fno_models import Contract, ContractQuote, OptionType
from fno_n11 import lot_ceiling, paper_positive, second_lot, stand_aside, vol_up
from fno_risk import lots_for_pool


def stamp(value):
    return datetime.fromisoformat(value)


def native_lots(pool, ask, lot_size, multiplier, ceiling, held_premium):
    cap = settings.FNO_MAX_LOTS_PROVEN if multiplier > 1.0 else settings.FNO_MAX_LOTS
    cap = min(cap, ceiling)
    lots = lots_for_pool(pool, ask, lot_size, settings.FNO_STOP_PREMIUM_PCT,
                         settings.FNO_MAX_RISK_PCT * multiplier, cap,
                         settings.FNO_MAX_LOSS_PER_TRADE * multiplier)
    if not lots and 0 < multiplier < 1:
        lots = lots_for_pool(pool, ask, lot_size, settings.FNO_STOP_PREMIUM_PCT, settings.FNO_MAX_RISK_PCT, 1)
    while lots > 0 and held_premium + lots * ask * lot_size > settings.FNO_MAX_OPEN_PREMIUM_PCT * pool:
        lots -= 1
    return lots


def tolerance_context(row, pool, held_premium, multiplier, ceiling, lots, volatile, positive):
    if row["underlying"] != "NIFTY":
        return None, "NIFTY paper only"
    ask, lot = row["entry_premium"], row["lot_size"]
    contract = Contract(row["token"], row["tradingsymbol"], row["underlying"], date.fromisoformat(row["expiry"]),
                        row["strike"], row["opt_type"], lot)
    first = EntryPlan(True, "", quote=ContractQuote(contract=contract, ask=ask),
                      opt_type=OptionType(row["opt_type"]), delta=row["delta_at_entry"], lots=lots, lot_size=lot)
    state = EntryState(pool, held_premium, 0, 0, (), frozenset(), True, False, risk_multiplier=multiplier)
    stop_points = abs(row["entry_underlying"] - row["stop_underlying"])
    upgrade = second_lot(first, state, stop_points=stop_points, ceiling=ceiling,
                         is_vol_up=volatile, is_paper_positive=positive)
    if upgrade:
        return upgrade, upgrade.reason
    if lots != 1:
        return None, "native size already two"
    if ceiling < 2:
        return None, "one-lot ceiling"
    if held_premium + 2 * ask * lot > settings.FNO_MAX_OPEN_PREMIUM_PCT * pool:
        return None, "open-premium cap"
    return None, "native tolerance checks"


def audit_position(row, positions, inputs, base, cash):
    pos, at = row["id"], stamp(row["entry_time"])
    production, = [item for item in inputs["positions"] if item["id"] == pos]
    reserve, = [item for item in inputs["admissions"] if item["position_ref"] == f"fno_position:{pos}"]
    adx, = [item for item in inputs["adx"] if item["session_date"] == row["entry_date"]]
    vol, = [item for item in inputs["volatility"] if item["session_date"] == row["entry_date"]]
    if production["entry_time"] != row["entry_time"] or stamp(adx["recorded_at"]) > at or stamp(vol["recorded_at"]) > at:
        raise ValueError(f"Decision clock or prior gate unavailable: {pos}")
    if adx["side"] != "HIGH" or adx["adx14"] < adx["threshold"] or adx["last_bar"] >= row["entry_date"]:
        raise ValueError(f"Observed trend state disagrees with entry-signal replay: {pos}")
    volatile = vol_up(vol["atr_pct"], vol["usual"])
    above = vol_up(vol["atr_pct"], vol["usual"], settings.FNO_N11_STAND_RATIO)
    if (volatile, above) != (bool(vol["vol_up"]), bool(vol["above_line"])):
        raise ValueError(f"Volatility gate disagreement: {pos}")
    prior = [item for item in inputs["paper_history"] if stamp(item["exit_time"]) < at]
    need = settings.FNO_N11_STAND_NEED
    nets = [item["net"] for item in prior]
    if stand_aside(above, nets, need):
        raise ValueError(f"Expected stand-aside: {pos}")
    visible = [item for item in cash if item.at < at]
    allocation = settings.FNO_PAPER_BANKROLL
    pool = allocation + sum(item.pnl for item in visible)
    if abs(pool - base["pool"]) > .01:
        raise ValueError(f"Shared equity differs: {pos}")
    stance = risk_stance(visible, allocation=allocation, now=at, policy=policy_from_settings())
    realised = sum(item.pnl for item in visible if item.single_leg and item.at.date() == at.date())
    ceiling = lot_ceiling(row["strategy"], at.hour * 60 + at.minute, volatile, realised)
    held = [item for item in positions if stamp(item["entry_time"]) < at < stamp(item["exit_time"])]
    premium = sum(item["entry_premium"] * item["initial_qty"] for item in held)
    ask, lot = row["entry_premium"], row["lot_size"]
    native = native_lots(pool, ask, lot, stance.multiplier, ceiling, premium)
    upgrade, why = tolerance_context(row, pool, premium, stance.multiplier, ceiling, native,
                                    volatile, paper_positive(nets, need))
    final_lots = upgrade.plan.lots if upgrade else native
    expected = [item["reason"] for item in inputs["second_lots"] if item["position_id"] == pos]
    if final_lots != row["initial_lots"] or expected != ([upgrade.reason] if upgrade else []):
        raise ValueError(f"Recomputed native or tolerance lots differ: {pos}")
    premium_cost = ask * final_lots * lot
    fees = calc_fno_costs(ask, 0, final_lots * lot, exchange=options_exchange_for(row["underlying"]))
    if (reserve["reserve_state"], reserve["dispatch_state"], reserve["outcome"], reserve["tradingsymbol"]) != (
        "CONSUMED", "FILLED", "filled", row["tradingsymbol"]
    ) or not stamp(reserve["created_at"]) <= stamp(reserve["claimed_at"]) <= stamp(reserve["resolved_at"]):
        raise ValueError(f"Reservation or dispatch proof differs: {pos}")
    if (abs(reserve["planned_premium_rs"] - premium_cost) > .01 or
            abs(reserve["worst_case_cash_rs"] - premium_cost - fees) > .01 or
            abs(production["risk_fee_reserve_rupees"] - fees) > .01):
        raise ValueError(f"Venue-specific reserved cash differs: {pos}")
    return {"id": pos, "adx": round(adx["adx14"], 6), "volatility_ratio": round(vol["atr_pct"] / vol["usual"], 6),
            "prior_20_net": round(sum(nets[-need:]), 2),
            "prior_20_sources": dict(Counter(item["source"] for item in prior[-need:])),
            "pool": round(pool, 2), "risk_multiplier": stance.multiplier, "day_realised_singles": round(realised, 2),
            "held_single_ids": [item["id"] for item in held], "held_premium": round(premium, 2),
            "open_premium_cap": round(settings.FNO_MAX_OPEN_PREMIUM_PCT * pool, 2),
            "two_lot_committed_premium": round(premium + 2 * ask * lot, 2),
            "native_ceiling": ceiling, "native_lots": native, "final_lots": final_lots,
            "tolerance": why, "reserved_cash": round(reserve["worst_case_cash_rs"], 2)}


def audit(folder, path):
    inputs = json.loads(path.read_bytes())
    for name, value in inputs["settings"].items():
        if getattr(settings, name) != value:
            raise ValueError(f"Dev and observed Production settings differ: {name}")
    base = json.loads((HERE / "deployed-control-nov5.json").read_bytes())
    manifest = folder / "manifest.json"
    db_path = folder / "fno-replay.sqlite"
    if digest(manifest) != base["manifest_sha256"] or digest(db_path) != json.loads(
        manifest.read_bytes()
    )["files_sha256"]["fno-replay.sqlite"]:
        raise ValueError("Changed position export")
    with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        positions = db.execute("SELECT * FROM fno_positions WHERE id BETWEEN 55 AND 59 AND source='FNO_PAPER' "
                               "ORDER BY id").fetchall()
    if tuple(row["id"] for row in positions) != IDS:
        raise ValueError("Unexpected position selection")
    cash = [Close(stamp(row["exit_time"]), row["pnl"], True) for row in positions]
    cash.extend(Close(stamp(row["closed"]), row["net"], False) for row in base["defined_risk_cash"])
    return {"inputs_sha256": digest(path), "export_manifest_sha256": digest(manifest),
            "scope": "Sizing and reservations conditional on the observed selected contract",
            "positions": [audit_position(row, positions, inputs, prior, cash)
                          for row, prior in zip(positions, base["positions"], strict=True)]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("export", type=Path)
    report = audit(parser.parse_args().export, HERE / "deployed-risk-inputs.json")
    path = HERE / "deployed-risk-audit.json"
    if path.is_file():
        if json.loads(path.read_bytes()) != report:
            raise ValueError("Recomputed sizing audit differs")
    else:
        with path.open("x", encoding="utf-8") as file:
            json.dump(report, file, indent=2, sort_keys=True)
            file.write("\n")
    print("matched sizing and reserved cash for", len(report["positions"]), "positions")


if __name__ == "__main__":
    main()
