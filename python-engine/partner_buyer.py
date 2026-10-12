"""[O12-PB 2026-10-12] Partner messages for an intraday option BUYER.

The partner no longer hedges and trades only long calls/puts. The advice
pipeline (signal, validation, caps, dedup, lifecycle, outcome tracking) is
unchanged; this module only decides what the partner reads, so each message
can be acted on in a few seconds during market hours:

  - entry card: one option to buy, a price limit, stop and target, risk per
    lot and a fill-by time, in about six short lines;
  - updates: one line each (exit, book, square off);
  - morning plan, OI flow pulse and close wrap: two lines per index.

Levels. The signal reads 5-minute bars of the front-month FUTURE, which
trades 50-150 points above the index the partner watches (Oct 9: about 60
points, more than that card's 47-point stop distance). Levels are therefore
shifted to the index using the option chain's put-call parity forward,
discounted to spot, and marked "≈". When parity is unavailable the levels
stay on the future and say "fut".

Premiums at stop/target are Black-76 estimates at today's implied
volatility. The stop estimate errs early (theta only lowers the premium).
The target estimate can overstate: on Oct 9 the option was ₹125 when the
future reached the target, against about ₹147 at constant volatility. So
the target is quoted on the index first and the premium is marked "≈".

Pure functions only: no network, database or settings reads.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Optional

import options_math
from fno_chain import RISK_FREE_RATE, years_to_expiry

VERSION = "BUYER_VIEW_V1"
BUY_LIMIT_RISK_SHARE = 0.15     # chase at most 15% of the per-unit stop distance
BUY_LIMIT_MAX_PCT = 0.04        # and never more than 4% above the ask
BUY_LIMIT_NO_STOP_PCT = 0.02    # limit when no premium stop could be estimated
MAX_PARITY_GAP_PCT = 0.02       # a futures-to-index gap above 2% is a bad parity read
FLOW_LEAN_VOTES = 2             # net OI-flow votes needed to name a side


def _px(value: float) -> str:
    """Option price for a broker ticket: 97.35, 101, 67.4."""
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _est(value: float) -> str:
    """A modelled premium: whole rupees, so it never reads as a quote."""
    return f"{value:,.0f}" if value >= 20 else f"{value:.1f}"


def _lvl(value: float) -> str:
    return f"{value:,.0f}"


def _round_to_tick(value: float, tick: float, *, up: bool = False) -> float:
    steps = round(value / tick, 6)
    return round((math.ceil(steps) if up else round(steps)) * tick, 2)


def fut_to_index_offset(snapshot, now: datetime) -> Optional[float]:
    """Futures minus index, from the chain's parity forward discounted to spot.

    ``None`` when parity is missing or implausible; callers then keep levels
    on the future and say so.
    """
    parity = getattr(snapshot, "parity_forward", None)
    forward = getattr(snapshot, "forward", None)
    if not parity or not forward or parity <= 0 or forward <= 0:
        return None
    T = years_to_expiry(snapshot.expiry, now)
    spot = parity * math.exp(-RISK_FREE_RATE * T)
    offset = forward - spot
    if not math.isfinite(offset) or abs(offset) > MAX_PARITY_GAP_PCT * forward:
        return None
    return round(offset, 2)


def level_label(name: str, value: Optional[float], basis: str) -> str:
    if value is None:
        return f"{name} n/a"
    return f"{name} ≈{_lvl(value)}" if basis == "INDEX" else f"{name} fut {_lvl(value)}"


def buyer_plan(candidate, snapshot, now: datetime, *, entry_window_min: int) -> Optional[dict]:
    """The single option a buyer takes on a directional card, with prices.

    ``candidate`` is the validated advisory (its BUY leg is the at-the-money
    option on the signal's side); ``snapshot`` is the chain it was built from.
    Returns a JSON-safe dict stored on the card's payload, or ``None`` when the
    card has no usable long option.
    """
    if getattr(candidate, "direction", None) not in ("LONG", "SHORT"):
        return None
    legs = [leg for leg in candidate.legs if leg.side == "BUY"]
    if not legs or legs[0].ask <= 0 or legs[0].lot_size <= 0:
        return None
    leg = legs[0]
    is_call = leg.option_type == "CE"
    fut = float(snapshot.forward)
    offset = fut_to_index_offset(snapshot, now)
    basis = "INDEX" if offset is not None else "FUTURES"
    # The option prices off its own expiry's forward, not the monthly future.
    option_forward = float(snapshot.parity_forward) if offset is not None else fut
    T = years_to_expiry(date.fromisoformat(leg.expiry), now)
    mid = (leg.bid + leg.ask) / 2.0 if leg.bid > 0 else leg.ask
    iv = options_math.implied_vol(mid, option_forward, leg.strike, T, RISK_FREE_RATE, is_call) if T > 0 else None

    def premium_at(fut_level: Optional[float]) -> Optional[float]:
        if iv is None or not fut_level or fut_level <= 0:
            return None
        moved = option_forward + (float(fut_level) - fut)
        if moved <= 0:
            return None
        value = options_math.black76_price(moved, leg.strike, T, iv, RISK_FREE_RATE, is_call)
        return value if math.isfinite(value) and value > 0 else None

    tick = leg.tick_size if leg.tick_size and leg.tick_size > 0 else 0.05
    stop = premium_at(candidate.invalidation_level)
    target = premium_at(candidate.target_level)
    # A stop at or above the ask, or a target at or below it, is no level at all.
    stop = _round_to_tick(stop, tick) if stop is not None and stop < leg.ask else None
    target = _round_to_tick(target, tick) if target is not None and target > leg.ask else None
    if stop is not None:
        limit = min(leg.ask + BUY_LIMIT_RISK_SHARE * (leg.ask - stop), leg.ask * (1 + BUY_LIMIT_MAX_PCT))
    else:
        limit = leg.ask * (1 + BUY_LIMIT_NO_STOP_PCT)
    limit = _round_to_tick(limit, tick, up=True)

    def to_index(value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        return round(float(value) - offset, 2) if offset is not None else round(float(value), 2)

    quote_at = candidate.quote_time
    fill_by = quote_at + timedelta(minutes=entry_window_min)
    if candidate.entry_deadline is not None:
        fill_by = min(fill_by, candidate.entry_deadline)
    expiry = date.fromisoformat(leg.expiry)
    return {
        "version": VERSION,
        "symbol": leg.tradingsymbol, "strike": leg.strike, "opt_type": leg.option_type,
        "expiry": leg.expiry, "dte": (expiry - now.date()).days,
        "lot_size": leg.lot_size, "tick_size": tick,
        "bid": leg.bid, "ask": leg.ask, "buy_limit": limit,
        "sl_premium": stop, "target_premium": target,
        "risk_per_lot": round((leg.ask - stop) * leg.lot_size, 2) if stop is not None else None,
        "iv": round(iv, 4) if iv is not None else None,
        "level_basis": basis, "fut_to_index_offset": offset,
        "trigger_index": to_index(candidate.trigger_level),
        "invalidation_index": to_index(candidate.invalidation_level),
        "target_index": to_index(candidate.target_level),
        "trigger_fut": candidate.trigger_level,
        "quote_at": quote_at.isoformat(), "fill_by": fill_by.isoformat(),
    }


def _option_name(underlying: str, view: dict) -> str:
    return f"{underlying} {view['strike']:g} {view['opt_type']}"


def _hhmm(value) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.strftime("%H:%M")


def _dte_note(dte: Optional[int]) -> str:
    if dte == 0:
        return "expiry today, scalp only"
    if dte == 1:
        return "expiry tomorrow, don't hold overnight"
    return ""


def render_buyer_card(label: str, view: dict, *, underlying: str, direction: str,
                      management_deadline) -> str:
    """The entry card: what to buy, the most to pay, where out, risk per lot."""
    long_view = direction == "LONG"
    basis = view["level_basis"]
    expiry = date.fromisoformat(view["expiry"]).strftime("%d %b")
    lines = [
        label,
        f"{'🟢' if long_view else '🔴'} BUY {_option_name(underlying, view)} ({expiry}) @ ₹{_px(view['ask'])}",
        f"Buy up to ₹{_px(view['buy_limit'])} · skip after {_hhmm(view['fill_by'])}",
    ]
    if view.get("trigger_index") is not None:
        side = "drops under" if long_view else "rises over"
        level = _lvl(view["trigger_index"])
        lines[-1] += (f" or if {underlying} {side} ≈{level}" if basis == "INDEX"
                      else f" or if {underlying} fut {side} {level}")
    stop_line = f"🛑 SL: {level_label(underlying, view['invalidation_index'], basis)}"
    if view.get("sl_premium") is not None:
        stop_line += f" or option ₹{_est(view['sl_premium'])}, whichever first"
    lines.append(stop_line)
    target_line = f"🎯 Target: {level_label(underlying, view['target_index'], basis)}"
    if view.get("target_premium") is not None:
        target_line += f" (option ≈₹{_est(view['target_premium'])})"
    lines.append(target_line)
    risk = f"Risk ≈₹{view['risk_per_lot']:,.0f}/lot ({view['lot_size']} qty) · " if view.get("risk_per_lot") else ""
    lines.append(f"{risk}exit by {_hhmm(management_deadline)} latest")
    why = [f"5-min close {'above' if long_view else 'below'} the opening range"]
    note = _dte_note(view.get("dte"))
    if note:
        why.append(note)
    stop, target, ask = view.get("sl_premium"), view.get("target_premium"), view["ask"]
    if stop is not None and target is not None and (target - ask) < (ask - stop):
        why.append("⚠ reward < risk in premium, size small")
    lines.append("Why: " + " · ".join(why))
    return "\n".join(lines)


def render_buyer_update(view: dict, event_type: str, *, underlying: str, observed_fut: float,
                        observed_at: datetime, management_deadline) -> str:
    """One line per lifecycle event, phrased as the action to take."""
    name = _option_name(underlying, view)
    if event_type not in ("INVALIDATION", "TARGET_ZONE"):
        return f"⏰ {name}: square off by {_hhmm(management_deadline)}. No overnight hold."
    offset = view.get("fut_to_index_offset")
    level = observed_fut - offset if offset is not None else observed_fut
    seen = f"{level_label(underlying, level, view['level_basis'])} at {_hhmm(observed_at)}"
    if event_type == "INVALIDATION":
        return f"🛑 EXIT {name} now: stop level hit ({seen}). Idea closed."
    return (f"🎯 {name}: target reached ({seen}). Book profit; on anything you keep, "
            f"move SL to ₹{_px(view['ask'])} (cost).")


def _premium_read(iv_read: str) -> str:
    return {"CHEAP": "premium cheap 🟢", "FAIR": "premium fair",
            "RICH": "premium rich, take profits quickly"}.get(iv_read, "")


def render_buyer_brief(day_label: str, rows: list[dict], *, crisis: bool, events_note: str = "") -> str:
    """Morning plan: per index, the two break levels and whether to buy premium.

    Row keys: name, error, basis, index_px, long_level, short_level (already on
    ``basis``), iv_read, dte, support, resistance, pcr.
    """
    lines = [f"☀️ Buyer plan · {day_label}"]
    if crisis:
        lines.append("🔴 Crisis regime: no cards today; avoid fresh long premium.")
    if events_note:
        lines.append(f"🗓 {events_note}")
    for row in rows:
        name = row["name"]
        if row.get("error"):
            lines.append(f"{name}: data unavailable")
            continue
        basis = row.get("basis", "FUTURES")
        head = level_label(name, row.get("index_px"), basis)
        if row.get("long_level") and row.get("short_level"):
            head += (f" · ▲ CE above {_lvl(row['long_level'])}"
                     f" · ▼ PE below {_lvl(row['short_level'])}")
        else:
            head += " · opening range not formed yet"
        lines.append(head)
        detail = [part for part in (_premium_read(row.get("iv_read", "")), _dte_note(row.get("dte"))) if part]
        if row.get("support") and row.get("resistance"):
            detail.append(f"OI walls {_lvl(row['support'])} / {_lvl(row['resistance'])}")
        if row.get("pcr") is not None:
            detail.append(f"PCR {row['pcr']:.2f}")
        if detail:
            lines.append("   " + " · ".join(detail))
    lines.append("Cards come only on a 5-min close past a level. Flat by 15:15.")
    return "\n".join(lines)


def flow_lean(votes: int) -> str:
    if votes >= FLOW_LEAN_VOTES:
        return "CALLS ▲"
    if votes <= -FLOW_LEAN_VOTES:
        return "PUTS ▼"
    return "NEUTRAL"


def render_flow_pulse(name: str, hhmm: str, lean: str, price: str, facts: list[str]) -> str:
    """OI flow in two lines: which side the writers favour, then why."""
    head = (f"📊 {name} {hhmm} · OI flow leans {lean}" if lean != "NEUTRAL"
            else f"📊 {name} {hhmm} · OI flow mixed, no side")
    return f"{head} ({price})\n" + " · ".join(facts)


def render_buyer_eod(day_label: str, rows: list[dict], record_line: str = "") -> str:
    """Close wrap: what each card did, in index and option-premium terms.

    Row keys: name, error, range_line, cards [{time, option, outcome, premium}],
    tomorrow_note.
    """
    lines = [f"🌙 Wrap · {day_label}"]
    for row in rows:
        name = row["name"]
        if row.get("error"):
            lines.append(f"{name}: data unavailable")
            continue
        lines.append(f"{name} {row.get('range_line', '')}".rstrip())
        cards = row.get("cards") or []
        for card in cards:
            text = f"   {card['time']} {card['option']}: {card['outcome']}"
            if card.get("premium"):
                text += f" · {card['premium']}"
            lines.append(text)
        if not cards:
            lines.append("   no card today (no clean break)")
        if row.get("tomorrow_note"):
            lines.append(f"   ⏳ {row['tomorrow_note']}")
    if record_line:
        lines.append(record_line)
    return "\n".join(lines)


def premium_path(paid: float, series: list) -> str:
    """'option ₹97 → peak ₹141, close ₹109' from 5-minute snapshot LTPs."""
    if not paid or paid <= 0 or not series:
        return ""
    ltps = [ltp for _, ltp in series]
    peak, last = max(ltps), ltps[-1]
    return (f"option ₹{_px(paid)} → peak ₹{_px(peak)} ({(peak - paid) / paid:+.0%}), "
            f"last ₹{_px(last)} ({(last - paid) / paid:+.0%})")


def range_line(day_low: float, day_high: float, close: float) -> str:
    """'fut range 22,480-22,650, closed near the high'."""
    span = day_high - day_low
    where = "mid-range"
    if span > 0:
        pos = (close - day_low) / span
        where = "near the high" if pos >= 0.75 else "near the low" if pos <= 0.25 else "mid-range"
    return f"fut range {_lvl(day_low)}–{_lvl(day_high)}, closed {_lvl(close)} ({where})"
