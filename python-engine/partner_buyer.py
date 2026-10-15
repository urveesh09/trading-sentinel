"""[O12-PB 2026-10-12] Partner messages for an intraday option BUYER.

The partner no longer hedges and trades only long calls/puts. The advice
pipeline (signal, validation, caps, dedup, lifecycle, outcome tracking) is
unchanged; this module only decides what the partner reads, so each message
can be acted on in a few seconds during market hours:

  - entry card: one option to buy, a price limit, stop and target, risk per
    lot and a fill-by time, in about six short lines;
  - updates: one line each (exit, book, square off);
  - morning plan, OI flow pulse and close wrap: two lines per index.

The partner trades with real money, so every number below was checked
against Production's own market records before release (read-only, Oct 5-12).

Levels. The signal reads 5-minute bars of the front-month FUTURE, which
trades above the index the partner watches: NIFTY by about 60 points on
Oct 9 (more than that card's 47-point stop distance), SENSEX by 330-430 on
Oct 8. Levels are shifted to the index by future minus spot, with spot
estimated as the chain's put-call parity forward discounted at
RISK_FREE_RATE, and marked "≈". Against the real SENSEX index on Oct 8 (184
samples) the estimate's median error was +0.4 points and its mean absolute
error 16 points (about 0.02%). When parity is unavailable the levels stay on
the future and say "fut".

Premiums at stop and target are Black-76 values at the option's mid implied
volatility, with PREMIUM_DECAY_MINUTES of time decay. Checked on 41,950 later
NIFTY/SENSEX snapshots:
  - target-like moves: median error 0.0% (NIFTY) and -1.7% (SENSEX), p10
    about -13%. The target is therefore quoted on the index first, with the
    premium as a range down to TARGET_PREMIUM_LOW_FACTOR.
  - stop-like moves: the real premium sits a median 3-4% under the model,
    so a premium stop fires a little before the index stop. That errs
    toward a smaller loss.
"Loss at SL" runs from the buy-up-to limit down to the premium stop, plus
one current bid-ask spread on exit and round-trip charges. With the premium
stop placed as an order, model error changes when the stop fires, not the
size of the loss. A fast fall can still fill below the trigger. On Oct 7 an
option went from ₹166 to ₹158 between two 5-minute prints, so it is shown
with "≈" and never called a maximum. Replayed on the five Oct 6-9 cards
(read-only), the premium stop protected every losing card. The index stop
alone was confirmed up to 28 minutes later, with the option ₹40 lower.

Pure functions only: no network or database reads.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Optional

import options_math
from fno_chain import RISK_FREE_RATE, years_to_expiry
from fno_costs import calc_fno_costs

VERSION = "BUYER_VIEW_V2"
BUY_LIMIT_RISK_SHARE = 0.15     # chase at most 15% of the per-unit stop distance
BUY_LIMIT_MAX_PCT = 0.04        # and never more than 4% above the ask
BUY_LIMIT_NO_STOP_PCT = 0.02    # limit when no premium stop could be estimated
MAX_PARITY_GAP_PCT = 0.02       # a futures-to-index gap above 2% is a bad parity read
PREMIUM_DECAY_MINUTES = 60      # time decay priced into the stop/target premiums
# Low end of the target premium range. Bulk p10 of target-like moves was
# -13.6% (NIFTY) and -11.9% (SENSEX). At the moment the index reached target,
# the Oct 6/8/9 cards' options were 10%, 14% and 15% under the model (each
# reached the model value later).
TARGET_PREMIUM_LOW_FACTOR = 0.85
NEAR_STOP_PCT = 0.05            # a premium stop within 5% of the ask is noise distance
FLOW_LEAN_VOTES = 2             # net OI-flow votes needed to name a side
_MINUTES_PER_YEAR = 365.0 * 24 * 60


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


def max_loss_per_lot(buy_limit: float, sl_premium: Optional[float], spread: float, lot_size: int,
                     exchange: str = "NFO") -> Optional[float]:
    """Loss per lot if filled at the limit and stopped at the premium stop.

    The exit sells one current bid-ask spread under the stop, and both legs
    pay round-trip charges on the contract's own exchange (BFO for SENSEX,
    O13-B3). ``None`` when no premium stop exists, because an index-only stop
    has no rupee bound.
    """
    if sl_premium is None or lot_size <= 0:
        return None
    exit_price = max(sl_premium - max(spread, 0.0), 0.0)
    return round((buy_limit - exit_price) * lot_size
                 + calc_fno_costs(buy_limit, exit_price, lot_size, exchange=exchange), 2)


def _segment(candidate) -> str:
    segment = str(getattr(candidate, "segment", "") or "").upper()
    if segment in ("NFO", "BFO"):
        return segment
    from fno_costs import options_exchange_for
    return options_exchange_for(getattr(candidate, "underlying", ""))


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
    # Price the levels an hour on; never past the expiry cutoff.
    T_level = max(T - PREMIUM_DECAY_MINUTES / _MINUTES_PER_YEAR, T / 2)

    def premium_at(fut_level: Optional[float]) -> Optional[float]:
        if iv is None or not fut_level or fut_level <= 0:
            return None
        moved = option_forward + (float(fut_level) - fut)
        if moved <= 0:
            return None
        value = options_math.black76_price(moved, leg.strike, T_level, iv, RISK_FREE_RATE, is_call)
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
        "target_premium_low": (_round_to_tick(target * TARGET_PREMIUM_LOW_FACTOR, tick)
                               if target is not None else None),
        "max_loss_per_lot": max_loss_per_lot(limit, stop, leg.ask - leg.bid if leg.bid > 0 else tick,
                                             leg.lot_size, exchange=_segment(candidate)),
        "fee_segment": _segment(candidate),
        "iv": round(iv, 4) if iv is not None else None,
        "level_basis": basis, "fut_to_index_offset": offset,
        "trigger_index": to_index(candidate.trigger_level),
        "invalidation_index": to_index(candidate.invalidation_level),
        "target_index": to_index(candidate.target_level),
        "trigger_fut": candidate.trigger_level,
        "quote_at": quote_at.isoformat(), "fill_by": fill_by.isoformat(),
    }


FALLBACK_VERSION = "BUYER_VIEW_FALLBACK_V1"


def fallback_view(candidate, now: datetime, *, entry_window_min: int) -> Optional[dict]:
    """[O13 2026-10-15] An unpriced one-option view from the card's own BUY
    leg and published levels, for when ``buyer_plan`` fails or its view
    cannot be rendered. Levels stay on the future; there is no premium stop,
    target premium or loss-per-lot estimate. Before this, such a card fell
    back to the two-leg spread card, which tells an option buyer to SELL.
    """
    if getattr(candidate, "direction", None) not in ("LONG", "SHORT"):
        return None
    legs = [leg for leg in candidate.legs if leg.side == "BUY"]
    if not legs or legs[0].ask <= 0 or legs[0].lot_size <= 0:
        return None
    leg = legs[0]
    tick = leg.tick_size if leg.tick_size and leg.tick_size > 0 else 0.05
    fill_by = candidate.quote_time + timedelta(minutes=entry_window_min)
    if candidate.entry_deadline is not None:
        fill_by = min(fill_by, candidate.entry_deadline)
    return {
        "version": FALLBACK_VERSION,
        "symbol": leg.tradingsymbol, "strike": leg.strike, "opt_type": leg.option_type,
        "expiry": leg.expiry, "dte": (date.fromisoformat(leg.expiry) - now.date()).days,
        "lot_size": leg.lot_size, "tick_size": tick, "bid": leg.bid, "ask": leg.ask,
        "buy_limit": _round_to_tick(leg.ask * (1 + BUY_LIMIT_NO_STOP_PCT), tick, up=True),
        "sl_premium": None, "target_premium": None, "target_premium_low": None,
        "max_loss_per_lot": None, "iv": None,
        "level_basis": "FUTURES", "fut_to_index_offset": None,
        "trigger_index": candidate.trigger_level, "invalidation_index": candidate.invalidation_level,
        "target_index": candidate.target_level, "trigger_fut": candidate.trigger_level,
        "quote_at": candidate.quote_time.isoformat(), "fill_by": fill_by.isoformat(),
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
    index_stop = level_label(underlying, view["invalidation_index"], basis)
    if view.get("sl_premium") is not None:
        # The premium stop is the protection: the index stop is only confirmed
        # on a 5-minute close (Oct 7: ₹158 premium stop at 14:02, the index
        # stop seen at 14:30 with the put at ₹117).
        lines.append(f"🛑 SL order at ₹{_px(view['sl_premium'])} right after buying "
                     f"(or exit if {index_stop} breaks)")
    else:
        lines.append(f"🛑 SL: exit if {index_stop} breaks")
    target_line = f"🎯 Target: {level_label(underlying, view['target_index'], basis)}"
    low, high = view.get("target_premium_low"), view.get("target_premium")
    if low is not None and high is not None:
        target_line += f" (option ≈₹{_est(low)}–{_est(high)})"
    lines.append(target_line)
    risk = (f"Loss at SL ≈₹{view['max_loss_per_lot']:,.0f}/lot ({view['lot_size']} qty, incl. charges) · "
            if view.get("max_loss_per_lot") else "")
    lines.append(f"{risk}exit by {_hhmm(management_deadline)} latest")
    why = [f"5-min close {'above' if long_view else 'below'} the opening range"]
    note = _dte_note(view.get("dte"))
    if note:
        why.append(note)
    stop, paid = view.get("sl_premium"), view["buy_limit"]
    if view.get("version") == FALLBACK_VERSION:
        why.append("⚠ premium stop not priced, size small")
    elif stop is not None and (view["ask"] - stop) < NEAR_STOP_PCT * view["ask"]:
        why.append(f"⚠ stop only ₹{_px(view['ask'] - stop)} under the price, skip or tiny size")
    elif stop is not None and low is not None and (low - paid) < (paid - stop):
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
            "move SL to your entry price.")


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
            detail.append(f"near-money PCR {row['pcr']:.2f}")
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


STOP_SAMPLE_MAX_AGE_SEC = 600      # two 5-minute samples


def _sample_age_sec(sample_ts: str, at: str) -> Optional[float]:
    try:
        return (datetime.fromisoformat(str(at)) - datetime.fromisoformat(str(sample_ts))).total_seconds()
    except ValueError:
        return None


def premium_path(paid: float, series: list, stopped_at: Optional[str] = None,
                 exit_by: Optional[str] = None) -> str:
    """'option ₹97 → peak ₹141, close ₹109' from 5-minute snapshot LTPs.

    [O13-B1] ``stopped_at`` ('YYYY-MM-DD HH:MM:SS', same clock as the
    series) ends the held path at the stop: the card told the buyer to exit
    there, so a later recovery is shown as after-exit, not held, never as
    the card's peak. Oct 13: both cards stopped at 11:45 and recovered past
    target by 14:40.

    [O15-B2] The last sample before the stop carries its own time. One
    older than STOP_SAMPLE_MAX_AGE_SEC is not a stop price (the review
    probe showed a 10:00 print labelled "at the stop" for an 11:45 stop),
    so the line says no price was seen near the stop.

    [O15] ``exit_by`` (the card's square-off deadline, same clock) ends a
    path with no stop: prints after it are not the card's result (Oct 15:
    the last print, 15:27, came after the 15:15 exit).
    """
    if not paid or paid <= 0 or not series:
        return ""

    def pct(price: float) -> str:
        return f"{(price - paid) / paid:+.0%}"

    def before_exit(ts) -> bool:
        return not exit_by or str(ts) <= exit_by

    if stopped_at:
        held = [(ts, ltp) for ts, ltp in series if str(ts) <= stopped_at]
        after = [ltp for ts, ltp in series if str(ts) > stopped_at and before_exit(ts)]
        if not held:
            return ""
        ts, ltp = held[-1]
        age = _sample_age_sec(ts, stopped_at)
        if age is not None and age <= STOP_SAMPLE_MAX_AGE_SEC:
            text = f"option ₹{_px(paid)} → ₹{_px(ltp)} at {str(ts)[11:16]}, just before the stop ({pct(ltp)})"
        else:
            text = (f"option ₹{_px(paid)} → last seen ₹{_px(ltp)} at {str(ts)[11:16]} ({pct(ltp)}); "
                    "no price seen near the stop")
        if after:
            peak = max(after)
            text += f"; after exit (not held) peak ₹{_px(peak)} ({pct(peak)})"
        return text
    held = [(ts, ltp) for ts, ltp in series if before_exit(ts)]
    if not held:
        return ""
    peak = max(ltp for _, ltp in held)
    last_ts, last = held[-1]
    if len(held) < len(series):
        return (f"option ₹{_px(paid)} → peak ₹{_px(peak)} ({pct(peak)}), "
                f"₹{_px(last)} at {str(last_ts)[11:16]} before the {exit_by[11:16]} exit ({pct(last)})")
    return (f"option ₹{_px(paid)} → peak ₹{_px(peak)} ({pct(peak)}), "
            f"last ₹{_px(last)} ({pct(last)})")


def range_line(day_low: float, day_high: float, close: float) -> str:
    """'fut range 22,480-22,650, closed near the high'."""
    span = day_high - day_low
    where = "mid-range"
    if span > 0:
        pos = (close - day_low) / span
        where = "near the high" if pos >= 0.75 else "near the low" if pos <= 0.25 else "mid-range"
    return f"fut range {_lvl(day_low)}–{_lvl(day_high)}, closed {_lvl(close)} ({where})"
