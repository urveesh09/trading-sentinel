from copy import deepcopy
from datetime import date, timedelta

import pytest

from test_shared_control import NOW
from cost_schedules import options_cost_snapshot
from fno_costs import calc_fno_costs_from_snapshot
from fno_exit_paths import N11_QUOTE_SCHEMA, params_digest
from fno_exit_rules import live_single_leg_exit_params
from fno_models import Contract
from config import settings
from trend_held_replay import evaluate_position


FEES = options_cost_snapshot()
FRONT = Contract(77, "NIFTY26SEPFUT", "NIFTY", date(2026, 9, 29), 0., "FUT", 65)
ENTRY = NOW.replace(second=0)


def position(strategy, exit_at, bid, reason):
    return {"id": 7, "source": "FNO_PAPER", "status": "CLOSED", "strategy": strategy, "underlying": "NIFTY",
            "direction": "LONG", "token": 82, "tradingsymbol": "NIFTY26SEP22600CE", "expiry": "2026-09-22",
            "qty": 65, "lot_size": 65, "initial_qty": 65, "initial_lots": 1, "lots": 1,
            "entry_time": ENTRY.isoformat(), "exit_time": exit_at.isoformat(), "exit_premium": bid,
            "exit_reason": reason, "pnl": (bid - 200) * 65 - calc_fno_costs_from_snapshot(200, bid, 65, FEES),
            "entry_premium": 200., "entry_underlying": 22600., "stop_underlying": 22560.,
            "target_underlying": 22800., "premium_stop": 150., "atr_at_entry": 30.}


def evidence(p, at, bid, future, *, reason="", params=None, first=False):
    def packet(token):
        return {"provider_at": (at - timedelta(seconds=1)).isoformat(), "received_at": at.isoformat(),
                "packet_present": True, "provider_token": token}
    row = {field: p[field] for field in ("source", "token", "tradingsymbol", "underlying", "direction")}
    row.update(at=at.isoformat(), position_id=p["id"], bid=bid, fut=future, exit_reason=reason,
               quote_evidence={"schema": N11_QUOTE_SCHEMA, "held_qty": p["qty"], "held_lot_size": p["lot_size"],
                               "held_expiry": p["expiry"], "strategy": p["strategy"],
                               "option": {**packet(p["token"]), "bid": bid, "bid_qty": p["qty"]},
                               "future": {**packet(FRONT.token), "token": FRONT.token, "tradingsymbol": FRONT.tradingsymbol,
                                          "underlying": FRONT.name, "expiry": FRONT.expiry.isoformat(), "ltp": future}})
    if params is not None:
        row["params_sha"] = params_digest(params)
        if first:
            row["params"] = params
    return row


def trend_case():
    params = {**live_single_leg_exit_params(settings), "FNO_HARD_FLAT_MIN": 910, "FNO_PROFIT_LOCK_ENABLED": True,
              "FNO_PROFIT_LOCK_ARM_R": .4, "FNO_PROFIT_LOCK_KEEP_FRACTION": .5, "FNO_PROFIT_LOCK_CONFIRM_SEC": 8.}
    p = position("N11_OR20", ENTRY + timedelta(seconds=910), 219., "profit_lock")
    held = [evidence(p, ENTRY + timedelta(seconds=second), 240. if second < 900 else 219.,
                     22600. + 10 * (second // 300), params=params, first=second == 0,
                     reason="profit_lock" if second == 910 else "") for second in range(0, 911, 10)]
    continuation = [evidence(p, ENTRY + timedelta(seconds=second), 212., 22630.) for second in (920, 930)]
    return p, held, continuation


def run(p, held, continuation, *, fees=FEES):
    return evaluate_position(p, held, continuation, front=FRONT, fees=fees)


def test_later_trend_exit_uses_same_contract_and_full_executable_bid():
    p, held, continuation = trend_case()
    out = run(p, held, continuation)
    assert out["status"] == "paired_fixed_entry"
    assert out["native"]["at"] == p["exit_time"] and out["native"]["net"] == p["pnl"]
    assert out["candidate"]["at"] == continuation[-1]["at"] and out["candidate"]["price"] == 212.
    assert out["net_delta"] < 0
    missing = run(p, held, [])
    assert missing["reason"] == "candidate_continuation_missing" and missing["net_delta"] is None


@pytest.mark.parametrize(("failure", "reason"), [
    ("shallow", "exit_bid_size_below_held_quantity"),
    ("late", "stale_or_future_quote"),
    ("future_receipt", "stale_or_future_quote"),
    ("crossed", "invalid_or_crossed_option_depth"),
    ("wrong_front", "front_future_mismatch"),
    ("clock_gap", "management_clock_gap"),
    ("native_pnl", "native_ledger_does_not_reconcile"),
    ("settings", "native_settings_digest_mismatch"),
    ("legacy", "held_quote_evidence_missing"),
])
def test_bad_evidence_withholds_net_delta(failure, reason):
    p, held, continuation = trend_case()
    if failure == "shallow":
        continuation[-1]["quote_evidence"]["option"]["bid_qty"] = 64
    elif failure == "late":
        clock = ENTRY + timedelta(seconds=920)
        option = continuation[0]["quote_evidence"]["option"]
        option["received_at"] = (clock - timedelta(seconds=8)).isoformat()
        option["provider_at"] = (clock - timedelta(seconds=16)).isoformat()
    elif failure == "future_receipt":
        continuation[0]["quote_evidence"]["option"]["received_at"] = continuation[-1]["at"]
    elif failure == "crossed":
        continuation[0]["quote_evidence"]["option"]["ask"] = 210.
    elif failure == "wrong_front":
        continuation[0]["quote_evidence"]["future"]["expiry"] = "2026-10-27"
    elif failure == "clock_gap":
        continuation.pop(0)
    elif failure == "native_pnl":
        p["pnl"] += 1
    elif failure == "settings":
        held[7]["params_sha"] = "different"
    else:
        held[0].pop("quote_evidence")
    out = run(p, held, continuation)
    assert out["status"] == "incomplete" and out["reason"] == reason and out["net_delta"] is None


def test_eff_soft_clock_is_reconstructed_from_each_tick_and_bound_fees():
    p = position("N11_EFF", ENTRY + timedelta(minutes=30), 190., "time_stop")
    params = {**live_single_leg_exit_params(settings), "FNO_HARD_FLAT_MIN": 910, "FNO_TIME_STOP_MIN": 60.}
    held = [evidence(p, ENTRY + timedelta(seconds=seconds), 190., 22600., first=seconds == 0, params=params)
            for seconds in range(0, 1800, 10)]
    held.append(evidence(p, ENTRY + timedelta(minutes=30), 190., 22600., reason="time_stop",
                         params={**params, "FNO_TIME_STOP_MIN": 30.}))
    out = run(p, held, [])
    assert out["status"] == "paired_fixed_entry" and out["net_delta"] == 0
    changed = deepcopy(FEES)
    changed["rates"]["brokerage_flat_per_order"] += 1
    assert run(p, held, [], fees=changed)["reason"] == "fee_schedule_mismatch"
