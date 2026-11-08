"""Strict fixed-entry replay for the frozen N012-A trend exit."""

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from types import SimpleNamespace

from cost_schedules import options_cost_snapshot
from fno_costs import calc_fno_costs_from_snapshot, options_exchange_for
from fno_exit_cadence import _state
from fno_exit_paths import N11_QUOTE_SCHEMA, params_digest
from fno_exit_rules import IST, evaluate_single_leg_exit
from fno_models import Contract
from fno_n11 import eff_clock, is_parent
from paired_control import frozen_rules


MAX_QUOTE_SEC = 10
MAX_LOOK_GAP_SEC = 12


class EvidenceGap(ValueError):
    """A missing or contradictory observation prevents a modeled fill."""


@dataclass(frozen=True)
class Look:
    at: datetime
    bid: float
    bid_qty: int
    future: float


def _clock(raw):
    try:
        value = datetime.fromisoformat(raw)
        if value.utcoffset() is not None:
            return value.astimezone(IST)
    except (TypeError, ValueError):
        pass
    raise EvidenceGap("missing_or_invalid_clock")


def _positive(value):
    return type(value) in (float, int) and isfinite(value) and value > 0


def _receipt(raw, token, at):
    if not isinstance(raw, dict) or raw.get("packet_present") is not True or raw.get("provider_token") != token:
        raise EvidenceGap("missing_or_wrong_quote_packet")
    provider, received = _clock(raw.get("provider_at")), _clock(raw.get("received_at"))
    if not provider <= received <= at or (at - provider).total_seconds() > MAX_QUOTE_SEC:
        raise EvidenceGap("stale_or_future_quote")
    return raw


def qualify_look(position, front: Contract, row, previous, *, first=False):
    at = _clock(row.get("at"))
    gap = (at - previous).total_seconds()
    if at.date() != previous.date() or not 0 <= gap <= MAX_LOOK_GAP_SEC or (not first and gap == 0):
        raise EvidenceGap("management_clock_gap")
    if (any(row.get(field) != position[field] for field in ("source", "token", "tradingsymbol", "underlying", "direction"))
            or row.get("position_id") != position["id"]):
        raise EvidenceGap("held_identity_mismatch")
    proof = row.get("quote_evidence")
    if not isinstance(proof, dict) or proof.get("schema") != N11_QUOTE_SCHEMA:
        raise EvidenceGap("held_quote_evidence_missing")
    for key in ("qty", "lot_size", "expiry"):
        if proof.get(f"held_{key}") != position[key]:
            raise EvidenceGap("held_contract_or_size_changed")
    if proof.get("strategy") != position["strategy"]:
        raise EvidenceGap("held_strategy_changed")
    option = _receipt(proof.get("option"), position["token"], at)
    future = _receipt(proof.get("future"), front.token, at)
    if (future.get("token"), future.get("tradingsymbol"), future.get("underlying"), future.get("expiry")) != (
        front.token, front.tradingsymbol, front.name, front.expiry.isoformat(),
    ):
        raise EvidenceGap("front_future_mismatch")
    bid, depth, price = option.get("bid"), option.get("bid_qty"), future.get("ltp")
    if not _positive(bid) or not _positive(price) or type(depth) is not int or depth <= 0:
        raise EvidenceGap("missing_price_or_bid_size")
    ask = option.get("ask")
    if ask is not None and (not _positive(ask) or ask < bid):
        raise EvidenceGap("invalid_or_crossed_option_depth")
    if row.get("bid") != round(bid, 4) or row.get("fut") != round(price, 4):
        raise EvidenceGap("quote_price_does_not_match_management")
    return Look(at, bid, depth, price)


class _ExitReplay:
    def __init__(self, position, entry, params, fees, *, rules=None):
        self.position, self.state = position, _state(position)
        self.entry, self.params, self.fees = entry, params, fees
        self.breach = None
        self.rules, self.trend = rules, rules.Trend() if rules else None

    def step(self, look, native_row=None):
        p, state = self.position, self.state
        params = self.params
        if p["strategy"] == "N11_EFF":
            sign = 1 if p["direction"] == "LONG" else -1
            risk = abs(state.entry_underlying - state.stop_underlying)
            progress = sign * (look.future - state.entry_underlying) / risk if risk > 0 else 0.
            soft_clock = eff_clock((look.at - self.entry).total_seconds() / 60, state.trail_active,
                                   look.bid, state.entry_premium, p["qty"], p["lots"], progress,
                                   exchange=options_exchange_for(p["underlying"]))
            params = {**params, "FNO_TIME_STOP_MIN": soft_clock}
        if native_row is not None and params_digest(params) != native_row.get("params_sha"):
            raise EvidenceGap("native_settings_digest_mismatch")
        if self.trend is not None:
            params = self.rules.trend_params(params, state, self.trend.update(look.at, look.future, p["direction"]))
        decision = evaluate_single_leg_exit(state, now_ist=look.at, fut_price=look.future, exit_px_basis=look.bid,
                                            hard_flat=look.at.hour * 60 + look.at.minute >= params["FNO_HARD_FLAT_MIN"],
                                            params=params, lock_breach_since=self.breach)
        if native_row is not None and native_row.get("exit_reason") != decision.exit_reason:
            raise EvidenceGap("native_decision_mismatch")
        if decision.exit_reason:
            if look.bid_qty < p["qty"]:
                raise EvidenceGap("exit_bid_size_below_held_quantity")
            fees = calc_fno_costs_from_snapshot(state.entry_premium, look.bid, p["qty"], self.fees)
            net = (look.bid - state.entry_premium) * p["qty"] - fees
            return {"at": look.at.isoformat(), "price": look.bid, "reason": decision.exit_reason, "net": net}
        self.breach = decision.lock_breach_since
        state.best_premium = decision.best_premium
        if decision.persist_trail:
            state.trail_active, state.trail_stop_underlying = decision.trail_active, decision.trail_stop
            state.best_underlying = decision.best_underlying
        return None


def evaluate_position(position, held, continuation, *, front: Contract, fees):
    """Score one closed native parent with fixed entry and independently bound quotes."""
    rules = frozen_rules()
    native = candidate = at = None
    try:
        p = position
        if (p["source"] != "FNO_PAPER" or p["status"] != "CLOSED" or not is_parent(SimpleNamespace(**p))
                or p["underlying"] not in {"NIFTY", "SENSEX"} or p["direction"] not in {"LONG", "SHORT"}):
            raise EvidenceGap("outside_closed_paper_parent_scope")
        entry, exit_at = _clock(p["entry_time"]), _clock(p["exit_time"])
        if (entry.date() != exit_at.date() or exit_at < entry or front.instrument_type != "FUT"
                or front.name != p["underlying"] or front.expiry <= entry.date()
                or date.fromisoformat(p["expiry"]) <= entry.date()):
            raise EvidenceGap("session_or_front_contract_mismatch")
        if (p["qty"] != p["initial_qty"] or p["lots"] != p["initial_lots"]
                or p["qty"] != p["lots"] * p["lot_size"] or not _positive(p["qty"])):
            raise EvidenceGap("held_quantity_does_not_match_entry")
        if not all(_positive(p[key]) for key in ("entry_premium", "entry_underlying", "stop_underlying",
                                                "target_underlying", "premium_stop")):
            raise EvidenceGap("invalid_entry_geometry")
        if fees != options_cost_snapshot(options_exchange_for(p["underlying"])):
            raise EvidenceGap("fee_schedule_mismatch")
        rows = tuple(held)
        if not rows or not isinstance(rows[0].get("params"), dict):
            raise EvidenceGap("native_settings_or_path_missing")
        params = rows[0]["params"]
        replay = _ExitReplay(p, entry, params, fees)
        looks, previous = [], entry
        for i, row in enumerate(rows):
            at = row.get("at")
            look = qualify_look(p, front, row, previous, first=i == 0)
            looks.append(look)
            previous = look.at
            native = replay.step(look, row)
            if native is not None and i != len(rows) - 1:
                raise EvidenceGap("native_exit_precedes_last_held_look")
        if (native is None or _clock(native["at"]) != exit_at or native["price"] != p["exit_premium"]
                or native["reason"] != p["exit_reason"] or not isfinite(p["pnl"])
                or abs(native["net"] - p["pnl"]) > .01):
            raise EvidenceGap("native_ledger_does_not_reconcile")
        replay = _ExitReplay(p, entry, params, fees, rules=rules)
        for look in looks:
            at = look.at.isoformat()
            candidate = replay.step(look)
            if candidate is not None:
                break
        if candidate is None:
            for row in continuation:
                at = row.get("at")
                look = qualify_look(p, front, row, previous)
                previous = look.at
                candidate = replay.step(look)
                if candidate is not None:
                    break
        if candidate is None:
            raise EvidenceGap("candidate_continuation_missing")
    except EvidenceGap as err:
        return {"status": "incomplete", "reason": str(err), "at": at, "net_delta": None}
    except (KeyError, ValueError, TypeError, AttributeError):
        return {"status": "incomplete", "reason": "invalid_position_or_quote_fields", "at": at, "net_delta": None}
    return {"status": "paired_fixed_entry", "native": native, "candidate": candidate,
            "net_delta": candidate["net"] - native["net"]}
