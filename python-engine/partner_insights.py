"""[O21-PX 2026-10-21] A deeper review: what the option did around each of
the partner's trades, what their order book shows, and the account behind it.

Sources, all read after the fact (nothing here places or changes an order):
  - the option's 1-minute candles for the session (the owner's market data,
    partner_trade_paths.py), else the 5-minute prints the analytics tick
    stored, marked as such;
  - the partner's Zerodha book: every option order with Zerodha's reason
    for a rejection, the price and trigger changes of modified orders, the
    positions and the day's cash (partner_broker_sync.py).

partner_coach.analyse() calls ``apply`` on each traded card or off-card
trade and ``day_details`` on each day. New flags (each with what happened,
why it matters with this trade's numbers, the better action and the rule):
  CHASED_SPIKE       bought after a fast run, near the high (off-card only:
                     on a card the buy-up-to price decides; 1-minute
                     candles only, prints can miss the high);
  GAVE_BACK_PROFIT   a trade well in profit closed below the entry (off-card
                     only: a card trade follows its card's plan);
  STOP_LOWERED       an SL order moved down while the trade was open;
  PRICE_RAISED_TO_FILL the buy price raised to get filled (on a card, only
                     past the card's buy-up-to);
  UNUSUAL_SIZE       [O24-SZ] much more money in one trade than the partner
                     usually puts in (replaces O21-PX's BIG_RISK, a fixed
                     tenth of the cash: the partner sizes as they choose);
  HELD_OVERNIGHT     an off-card option still held at the close;
  INSUFFICIENT_FUNDS (day) Zerodha refused a buy for want of money.
Positives: CUT_LOSS_SAVED (30 minutes after a losing exit the option was
much lower) and STOP_TRAILED (an SL order moved up).

``insight`` per trade: hold time, the best and worst price while holding,
the run before the buy, what the option did after the sale, the money at
risk against the day's cash, charges, the order changes and a small chart.

Hindsight only shows what happened and praises a disciplined exit; it never
tells the partner to hold a loser. A 1-minute candle can put a time up to a
minute early; 5-minute prints can miss a touch between them.

[A22-P5 2026-10-22] "While you held" uses only candles wholly inside the
holding (a print: a time inside it). The minute of the buy and the minute of
the sale also hold prices from before the buy or after the sale (Oct 22
audit: a 10-second hold was given the whole minute's high and low); a price
seen only there is reported apart as ``edge``, marked uncertain, and a
stop's later touch must start after the stop was moved and end before the
sale.

[O24-SR 2026-10-24] The trade's SL orders are every option sale that
carried a trigger (``partner_broker_sync.order_stop``): a fired stop shows as
LIMIT or MARKET with its trigger, and a stop turned into a sale shows its
trigger only in its changes. Before, only orders still typed SL or SL-M
counted, which hid most stop moves (Oct 23: one STOP_LOWERED where nine
trades had a stop moved down). [O24-RF] A refusal reads in plain words
(``refusal_plain``): a buy short of money, or a sale Zerodha counted as a
new short sale (another sell already waiting for the lot, more than held,
or bought and sold under different products). [O24-MC] The session ends at
15:40.

[O24-SB 2026-10-24] The usual size starts from the trades before the window
(``partner_coach.size_history``, each as ``trade_share`` computes it), so a
day's usual does not depend on which window it is read in. The usual is the
partner's habit, not a safe size.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median
from typing import Optional

from partner_coach import (IST, STOP_SLIPPAGE_PCT, _amt, _day_close, _dt, _flag, _hhmm, _instead, _orders, _pnl,
                           _positive, _px, _rs, _worked)

BASIS_CANDLES = "1MIN_CANDLES"
RUN_LOOKBACK_MIN = 15          # the run before a buy is measured over this window
SPIKE_RUN_PCT = 0.20           # CHASED_SPIKE: the option rose this much in that window
SPIKE_NEAR_HIGH = 0.95         # ... and the buy was at least this share of the day's high so far
SPIKE_MIN_BARS = 10            # ... with this many 1-minute candles in the window
AFTER_MIN = 30                 # what the option did after the sale
CUT_LOSS_SAVED_PCT = 0.15      # 30 minutes after a losing exit the option was this much lower
PROTECT_GAIN_PCT = 0.20        # GAVE_BACK_PROFIT: the open gain at which the stop goes to the entry
PRICE_RAISES_MIN = 2           # PRICE_RAISED_TO_FILL: raised this many times ...
PRICE_RAISE_PCT = 0.05         # ... or by this much in total
# [O24-SZ 2026-10-24] Size against the partner's own habit, not a fixed share
# of cash (owner: "they use the amount they have in proportion they like").
# The share of the day's cash put into a trade (premium paid) is compared with
# the median share of their last USUAL_SIZE_LOOKBACK trades; from the
# USUAL_SIZE_MIN_TRADES-th earlier trade on, more than USUAL_SIZE_MULT times
# that is UNUSUAL_SIZE. Declared, not fitted.
USUAL_SIZE_MULT = 1.5
USUAL_SIZE_MIN_TRADES = 5
USUAL_SIZE_LOOKBACK = 20
CHART_BEFORE_MIN = 20
CHART_AFTER_MIN = 30
STOP_CLOCK_SLACK = timedelta(seconds=60)
_FUNDS = re.compile(r"insufficient|margin|funds", re.IGNORECASE)
# [O24-RF] "Margin required: 159586.95. Margin available: 7536.70." in Zerodha's refusal.
_MARGIN = re.compile(r"margin required:\s*([0-9][0-9,]*(?:\.[0-9]+)?).*?margin available:\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
                     re.IGNORECASE | re.DOTALL)


@dataclass
class Context:
    """What partner_coach.load_partner_coach read for the window."""
    paths: dict = field(default_factory=dict)        # (day, exchange, symbol) -> {"basis", "bars"}
    orders: list = field(default_factory=list)       # partner_orders rows
    changes: dict = field(default_factory=dict)      # order_id -> partner_order_changes rows
    positions: dict = field(default_factory=dict)    # day -> partner_broker_positions rows
    accounts: dict = field(default_factory=dict)     # day -> partner_account_days row
    complete_days: frozenset = frozenset()
    now: Optional[datetime] = None
    watch: list = field(default_factory=list)        # [O24-PW] the trade watch's sent messages

    @classmethod
    def of(cls, context: Optional[dict], complete_days: frozenset = frozenset(),
           now: Optional[datetime] = None) -> "Context":
        context = context or {}
        return cls(paths=context.get("paths") or {}, orders=context.get("orders") or [],
                   changes=context.get("changes") or {}, positions=context.get("positions") or {},
                   accounts=context.get("accounts") or {}, complete_days=frozenset(complete_days), now=now,
                   watch=context.get("watch") or [])


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _minute(at: datetime) -> datetime:
    return at.astimezone(IST).replace(second=0, microsecond=0)


def _session(day: str, hour: int, minute: int) -> datetime:
    return IST.localize(datetime.fromisoformat(day) + timedelta(hours=hour, minutes=minute))


def _t(day: str, at: datetime) -> int:
    """Minutes since 09:15 on ``day`` (the chart's x axis)."""
    return int((at.astimezone(IST) - _session(day, 9, 15)).total_seconds() // 60)


def _clock(day: str, t: int) -> str:
    return _hhmm(_session(day, 9, 15) + timedelta(minutes=t))


def _pct(value: float, digits: int = 0) -> str:
    """A signed share with a true minus sign, as the rupee figures: "−16%", "+4.0%"."""
    return f"{'−' if value < 0 else '+'}{abs(value):.{digits}%}"


def _lots(lots: int) -> str:
    return f"{lots} lot{'s' if lots != 1 else ''}"


def when(ctx: Context, day: str) -> str:
    """[O23-PH] "today" for the session being read now, "that day" for an
    earlier one (the partner can open past reviews)."""
    if ctx.now is None or ctx.now.astimezone(IST).date().isoformat() == day:
        return "today"
    return "that day"


def cash_of(account: Optional[dict]) -> Optional[float]:
    """The day's cash: the opening balance plus money added today."""
    if not account:
        return None
    cash = float(account.get("opening_balance") or 0) + float(account.get("intraday_payin") or 0)
    return cash if cash > 0 else None


def _inside(bar: tuple, first: datetime, end: datetime, basis: Optional[str]) -> bool:
    """A 1-minute candle wholly inside [first, end]; a print at a time inside it."""
    if basis == BASIS_CANDLES:
        return first <= bar[0] and bar[0] + timedelta(minutes=1) <= end
    return first <= bar[0] <= end


def _edge(bar: tuple, first: datetime, end: datetime, basis: Optional[str]) -> bool:
    """A candle that overlaps the holding without being inside it (the buy or sale minute)."""
    return (basis == BASIS_CANDLES and not _inside(bar, first, end, basis)
            and bar[0] < end and bar[0] + timedelta(minutes=1) > first)


def _window(trade: dict, now: Optional[datetime]) -> tuple[datetime, datetime, bool]:
    """(first buy, end of the holding, closed?) for a trade with a buy; an
    open trade is held to the close, or to now during the session."""
    first = trade["first_buy_at"]
    closed = bool(trade["sells"]) and not trade["open_lots"] and trade.get("last_sell_at") is not None
    end = trade["last_sell_at"] if closed else _day_close(trade["session_date"])
    if not closed and now is not None:
        end = min(end, now)
    return first, max(end, first), closed


# ---------------------------------------------------------------------------
# per trade
# ---------------------------------------------------------------------------

def apply(item: dict, trade: Optional[dict], card: Optional[dict], stops: Optional[list], ctx: Context) -> None:
    """Add the path, order-book and account findings to one analysed trade."""
    if not trade or not trade["buys"] or trade.get("first_buy_at") is None or trade.get("avg_entry") is None:
        return
    day, exchange, symbol = trade["session_date"], trade["exchange"], trade.get("tradingsymbol")
    first, end, closed = _window(trade, ctx.now)
    lot_size = trade.get("lot_size") or (card or {}).get("lot_size")
    entry, exit_px, actual = trade["avg_entry"], trade["avg_exit"], trade["pnl"]
    bought_qty = trade["bought_lots"] * lot_size if lot_size else trade.get("qty")
    qty = trade.get("qty") or bought_qty
    first_px = next((b["price"] for b in trade["buys"] if b.get("price") is not None), entry)
    insight: dict = {"hold_min": round((end - first).total_seconds() / 60), "held_to_close": not closed,
                     "basis": None}
    if closed and exit_px is not None and qty and actual is not None:
        gross = round((exit_px - entry) * qty, 2)
        insight.update(gross_pnl=gross, charges=round(gross - actual, 2))
    path = ctx.paths.get((day, exchange, symbol)) if symbol else None
    bars = (path or {}).get("bars") or []
    if bars:
        insight["basis"] = path.get("basis")
        _path_facts(insight, bars, path.get("basis"), first, end, closed, entry, first_px, qty or bought_qty)
        insight["chart"] = _chart(day, bars, trade, card, stops, first, end)
    sl_orders = _stop_orders_of(ctx, trade, first, end)
    events = _order_events(ctx, trade, sl_orders, first, end)
    if events:
        insight["events"] = events
    _risk(insight, trade, card, stops, ctx.accounts.get(day), entry, bought_qty, lot_size, actual, exit_px, closed,
          when(ctx, day))
    item["insight"] = insight
    off_card = card is None
    if off_card or not card.get("buy_limit"):
        _chased_spike(item, path, bars, trade, first, first_px, actual)
    if off_card and closed and exit_px is not None and qty and bars:
        _gave_back(item, bars, trade, first, end, entry, exit_px, qty, actual)
    _stop_moves(item, sl_orders, ctx, trade, bars, (path or {}).get("basis"), first, end, closed, entry, exit_px,
                qty, actual)
    _price_raised(item, ctx, trade, card)
    if off_card:
        _held_overnight(item, trade, ctx)
    if closed and actual is not None and actual < 0 and exit_px is not None and qty and insight.get("after"):
        after = insight["after"]
        if after["price"] <= exit_px * (1 - CUT_LOSS_SAVED_PCT):
            item["positives"].append(_positive(
                "CUT_LOSS_SAVED", f"You sold at {_px(exit_px)} for {_rs(actual)}; {after['minutes']} minutes later "
                                  f"the option was {_px(after['price'])}. Getting out kept the loss about "
                                  f"{_amt((exit_px - after['price']) * qty)} smaller than holding to then."))


def _path_facts(insight: dict, bars: list, basis: Optional[str], first: datetime, end: datetime, closed: bool,
                entry: float, first_px: float, size: Optional[int]) -> None:
    m0, m1 = _minute(first), _minute(end)
    held = [b for b in bars if _inside(b, first, end, basis)]
    best = max(held, key=lambda b: b[2]) if held else None
    worst = min(held, key=lambda b: b[3]) if held else None
    if held and size:
        insight["best"] = {"at": _hhmm(best[0]), "price": best[2], "move_rs": round((best[2] - entry) * size, 2),
                           "pct": round(best[2] / entry - 1, 4)}
        insight["worst"] = {"at": _hhmm(worst[0]), "price": worst[3], "move_rs": round((worst[3] - entry) * size, 2),
                            "pct": round(worst[3] / entry - 1, 4)}
    edges = [b for b in bars if _edge(b, first, end, basis)]
    if edges:
        high, low = max(b[2] for b in edges), min(b[3] for b in edges)
        if best is None or high > best[2] or low < worst[3]:
            insight["edge"] = {"high": high, "low": low, "uncertain": True}
    before = [b for b in bars if m0 - timedelta(minutes=RUN_LOOKBACK_MIN) <= b[0] < m0]
    if before and first_px:
        low = min(b[3] for b in before)
        insight["before"] = {"minutes": RUN_LOOKBACK_MIN, "low": low, "run_pct": round(first_px / low - 1, 4)}
    if closed:
        after = [b for b in bars if m1 < b[0] <= m1 + timedelta(minutes=AFTER_MIN)]
        if after:
            insight["after"] = {"minutes": round((after[-1][0] - m1).total_seconds() / 60), "price": after[-1][4],
                                "at": _hhmm(after[-1][0]), "high": max(b[2] for b in after),
                                "low": min(b[3] for b in after)}


def _chart(day: str, bars: list, trade: dict, card: Optional[dict], stops: Optional[list], first: datetime,
           end: datetime) -> dict:
    lo = max(_session(day, 9, 15), _minute(first) - timedelta(minutes=CHART_BEFORE_MIN))
    hi = min(_day_close(day), _minute(end) + timedelta(minutes=CHART_AFTER_MIN))
    points = [[_t(day, b[0]), b[4]] for b in bars if lo <= b[0] <= hi]
    marks = []
    for kind, fills in (("buy", trade["buys"]), ("sell", trade["sells"])):
        for fill in fills:
            at = _dt(fill.get("at"))
            if at is not None and fill.get("price") is not None:
                marks.append({"t": _t(day, at), "at": _hhmm(at), "price": fill["price"], "kind": kind})
    levels = []
    if card:
        for key, label, kind in (("buy_limit", "Card buy-up-to", "limit"), ("sl_premium", "Card SL", "stop"),
                                 ("target_low", "Card target", "target")):
            if card.get(key):
                levels.append({"label": label, "price": float(card[key]), "kind": kind})
    for stop in stops or []:
        level = {"label": "Your stop", "price": float(stop["trigger_price"]), "kind": "your_stop"}
        if level not in levels:
            levels.append(level)
    span = [p[0] for p in points] + [m["t"] for m in marks]
    start_t, end_t = (min(span), max(span)) if span else (_t(day, lo), _t(day, hi))
    return {"points": points, "marks": marks, "levels": levels, "start": _clock(day, start_t),
            "end": _clock(day, end_t), "start_t": start_t, "end_t": end_t}


def _stop_orders_of(ctx: Context, trade: dict, first: datetime, end: datetime) -> list:
    """[O24-SR] The trade's SL orders, placed while it was open: resting,
    fired, cancelled or turned into a sale (partner_broker_sync.order_stop)."""
    from partner_broker_sync import order_stop
    out = []
    for order in ctx.orders:
        if order["exchange"] != trade["exchange"] or order["tradingsymbol"] != trade.get("tradingsymbol"):
            continue
        stop = order_stop(order, ctx.changes.get(order["order_id"], []))
        placed = _dt(stop["placed_at"]) if isinstance(stop, dict) else None
        if placed is not None and first - STOP_CLOCK_SLACK <= placed <= end:
            out.append(order)
    return out


def _order_events(ctx: Context, trade: dict, sl_orders: list, first: datetime, end: datetime) -> list:
    """Order changes and refusals on this option, for the trade's timeline."""
    events = []
    buy_ids = {b.get("order_id") for b in trade["buys"] if b.get("order_id")}
    for order_id in sorted(buy_ids):
        for change in ctx.changes.get(order_id, []):
            if change["field"] == "price":
                verb = "raised" if change["new_value"] > change["old_value"] else "lowered"
                events.append({"at": _hhmm(_dt(change["changed_at"])), "who": "you", "sort_key": change["changed_at"],
                               "text": f"You {verb} your buy price from {_px(change['old_value'])} to "
                                       f"{_px(change['new_value'])}"})
    for order in sl_orders:
        for change in ctx.changes.get(order["order_id"], []):
            if change["field"] == "trigger_price":
                verb = "raised" if change["new_value"] > change["old_value"] else "lowered"
                events.append({"at": _hhmm(_dt(change["changed_at"])), "who": "you", "sort_key": change["changed_at"],
                               "text": f"You {verb} your stop from {_px(change['old_value'])} to "
                                       f"{_px(change['new_value'])}"})
    window_start = first - timedelta(minutes=RUN_LOOKBACK_MIN)
    for order in ctx.orders:
        placed = _dt(order.get("placed_at"))
        if (order["status"] == "REJECTED" and order["exchange"] == trade["exchange"]
                and order["tradingsymbol"] == trade.get("tradingsymbol") and placed is not None
                and window_start <= placed <= end):
            plain = refusal_plain(order, ctx.orders)
            reason = f": {plain or order['status_message']}" if plain or order.get("status_message") else ""
            events.append({"at": _hhmm(placed), "who": "you", "sort_key": placed.isoformat(),
                           "text": f"Zerodha refused your {order['transaction_type'].lower()} order{reason}"})
    # [O24-PW] What the trade watch told the partner about this trade (its key is the first buy's order id).
    first_buy = next((b.get("order_id") for b in trade["buys"] if b.get("order_id")), None)
    for message in ctx.watch:
        at = _dt(message.get("created_at"))
        if first_buy and message.get("position_key") == first_buy and at is not None and message.get("summary"):
            events.append({"at": _hhmm(at), "who": "assistant", "sort_key": at.isoformat(),
                           "text": f"Assistant: {message['summary']}"})
    return sorted(events, key=lambda e: e["sort_key"])


def _filled_by(orders: list, side: str, at: datetime) -> int:
    """Quantity of these orders on one side that had filled by ``at`` (a fill
    is stamped with the order's last exchange update)."""
    total = 0
    for order in orders:
        filled_at = _dt(order.get("updated_at") or order.get("placed_at"))
        if order["transaction_type"] == side and filled_at is not None and filled_at <= at:
            total += int(order.get("filled_quantity") or 0)
    return total


def refusal_plain(order: dict, orders: list) -> Optional[str]:
    """[O24-RF] Why Zerodha refused an order for margin, in plain words, or
    None when the refusal is about something else (its own text then shows).

    A sale of an option the partner holds needs no margin, so a sale refused
    for margin was counted as a new short sale: the option was not held,
    the buy and the sale used different products, the sale was for more
    than was held, or (the rest) another sell order was already waiting for
    the lot."""
    found = _MARGIN.search(str(order.get("status_message") or ""))
    at = _dt(order.get("placed_at"))
    if not found or at is None:
        return None
    need, have = (float(value.replace(",", "")) for value in found.groups())
    if order["transaction_type"] == "BUY":
        return f"the buy needed {_amt(need)} and your account had {_amt(have)}."
    same = [o for o in orders if o["exchange"] == order["exchange"] and o["tradingsymbol"] == order["tradingsymbol"]
            and o["order_id"] != order["order_id"]]
    held = _filled_by(same, "BUY", at) - _filled_by(same, "SELL", at)
    qty = int(order.get("quantity") or 0)
    bought_as = {o.get("product") for o in same if o["transaction_type"] == "BUY" and o.get("product")
                 and (o.get("filled_quantity") or 0) > 0 and (_dt(o.get("updated_at") or o.get("placed_at")) or at) <= at}

    def short(what: str) -> str:
        return (f"Zerodha counted {what} as a new short sale, which needs {_amt(need)} of margin; your account had "
                f"{_amt(have)}.")

    if held <= 0:
        return f"you did not hold this option at that moment, so {short('the sale')}"
    if order.get("product") and bought_as and order["product"] not in bought_as:
        return (f"you bought it as {'/'.join(sorted(bought_as))} and sold it as {order['product']}, so "
                f"{short('the sale')}")
    if qty > held:
        return f"the sale was for {qty} and you held {held}, so {short(f'the extra {qty - held}')}"
    return (f"another sell order for this option was already waiting, so this one would have sold more than the "
            f"{held} you held: {short('it')}")


def _risk(insight: dict, trade: dict, card: Optional[dict], stops: Optional[list],
          account: Optional[dict], entry: float, bought_qty: Optional[int], lot_size: Optional[int],
          actual: Optional[float], exit_px: Optional[float], closed: bool, on_day: str = "today") -> None:
    """Money at risk: to the partner's own stop; with no stop order, the
    premium; when stops are unknown, to the card's SL on a card trade (the
    plan) and the premium off-card."""
    cash = cash_of(account)
    if not cash or not bought_qty:
        return
    live = [s for s in stops or [] if s.get("status") != "REJECTED"]
    card_sl = (card or {}).get("sl_premium")
    if live:
        trigger = float(live[0]["trigger_price"])
        risk, basis = max(entry - trigger, 0.0) * bought_qty, "STOP"
    elif stops is None and card_sl and entry > card_sl:
        trigger, risk, basis = float(card_sl), (entry - card_sl) * bought_qty, "CARD_SL"
    else:
        trigger, risk, basis = None, entry * bought_qty, ("NO_STOP" if stops is not None else "PREMIUM")
    pct = risk / cash
    insight["risk"] = {"rs": round(risk, 2), "pct_of_cash": round(pct, 4), "basis": basis, "cash": round(cash, 2),
                       "trigger": trigger}
    # [O24-SZ] What went into the trade, for the size against the partner's usual (usual_size_flags).
    paid = entry * bought_qty
    insight["size"] = {"rs": round(paid, 2), "pct_of_cash": round(paid / cash, 4), "cash": round(cash, 2),
                       "lots": trade["bought_lots"], "lot_size": lot_size, "entry": entry,
                       "exit": exit_px if closed else None, "actual": actual, "on_day": on_day}


def usual_size(shares: list) -> Optional[float]:
    """[O24-SZ] The share of cash the partner usually puts in one trade: the
    median of the last USUAL_SIZE_LOOKBACK, once there are USUAL_SIZE_MIN_TRADES."""
    recent = [s for s in shares if s and s > 0][-USUAL_SIZE_LOOKBACK:]
    return round(median(recent), 4) if len(recent) >= USUAL_SIZE_MIN_TRADES else None


def trade_share(trade: Optional[dict], account: Optional[dict]) -> Optional[float]:
    """[O24-SB] The money put into a trade as a share of that day's cash, as
    ``_risk`` puts it in ``insight["size"]`` (pure)."""
    if not trade or not trade["buys"] or trade.get("first_buy_at") is None or trade.get("avg_entry") is None:
        return None
    cash = cash_of(account)
    lot_size = trade.get("lot_size")
    bought_qty = trade["bought_lots"] * lot_size if lot_size else trade.get("qty")
    if not cash or not bought_qty:
        return None
    return round(trade["avg_entry"] * bought_qty / cash, 4)


def usual_size_flags(items: list, earlier: Optional[list] = None) -> None:
    """[O24-SZ] UNUSUAL_SIZE on each trade with much more in it than the
    partner's usual, judged against the trades before it (all days, in time
    order). Items carry ``_trade`` and ``insight["size"]``. [O24-SB]
    ``earlier``: the shares of the trades before the window, oldest first."""
    shares: list = list(earlier or [])
    for item in sorted((i for i in items if i.get("_trade") and (i.get("insight") or {}).get("size")),
                       key=lambda i: i["_trade"]["first_buy_at"]):
        size, trade = item["insight"]["size"], item["_trade"]
        usual = usual_size(shares)
        shares.append(size["pct_of_cash"])
        if usual is None or size["pct_of_cash"] <= USUAL_SIZE_MULT * usual:
            continue
        lots, lot_size, entry, actual = size["lots"], size["lot_size"], size["entry"], size["actual"]
        per_lot = entry * lot_size if lot_size else 0.0
        fit = int((usual * size["cash"]) // per_lot) if per_lot > 0 else 0
        better_pnl = None
        if 1 <= fit < lots and size["exit"] is not None:
            better_pnl = _pnl(entry, size["exit"], fit * lot_size, trade["exchange"], _orders(trade))
        if better_pnl is not None:
            better = f"{_lots(fit)}, about your usual size: {_instead(better_pnl, actual)}."
        elif 1 <= fit < lots:
            better = f"{_lots(fit)} would have been about your usual size."
        else:
            better = "Keep to the size you usually trade."
        item["flags"].append(_flag(
            "UNUSUAL_SIZE", f"{_lots(lots)} of {item.get('option')} at {_px(entry)}: {_amt(size['rs'])} in this "
                            f"trade, {size['pct_of_cash']:.0%} of your cash {size['on_day']}. You usually put about "
                            f"{usual:.0%} into one trade.",
            (round(actual - better_pnl, 2) if better_pnl is not None and actual is not None else None),
            why="A trade much bigger than your usual turns one bad move into a big loss." + _worked(actual),
            better=better, better_pnl=better_pnl, actual_pnl=actual if better_pnl is not None else None))


def _chased_spike(item: dict, path: Optional[dict], bars: list, trade: dict, first: datetime, first_px: float,
                  actual: Optional[float]) -> None:
    if not bars or (path or {}).get("basis") != BASIS_CANDLES or not first_px:
        return
    m0 = _minute(first)
    before = [b for b in bars if m0 - timedelta(minutes=RUN_LOOKBACK_MIN) <= b[0] < m0]
    so_far = [b for b in bars if b[0] < m0]
    if len(before) < SPIKE_MIN_BARS or not so_far:
        return
    low = min(b[3] for b in before)
    high = max(b[2] for b in so_far)
    run = first_px / low - 1
    if run < SPIKE_RUN_PCT or first_px < SPIKE_NEAR_HIGH * high:
        return
    where = (", at a new high for the day." if first_px >= high
             else f", {1 - first_px / high:.1%} under its high so far ({_px(high)}).")
    why = ("Buying right after a fast run is the FOMO pattern: the move is already in the price, and the first "
           "pullback often comes before any profit.")
    dip = [b for b in bars if m0 < b[0] <= m0 + timedelta(minutes=RUN_LOOKBACK_MIN)]
    if dip:
        dip_low = min(b[3] for b in dip)
        why += f" In the 15 minutes after your buy it traded as low as {_px(dip_low)} ({_pct(dip_low / first_px - 1)})."
    item["flags"].append(_flag(
        "CHASED_SPIKE", f"You bought at {_px(first_px)} at {_hhmm(first)}, after the option rose {run:.0%} in "
                        f"{RUN_LOOKBACK_MIN} minutes (from {_px(low)})" + where, None,
        why=why + _worked(actual),
        better="Wait for a card. After a spike, let the price settle before deciding; a missed move costs nothing."))


def _gave_back(item: dict, bars: list, trade: dict, first: datetime, end: datetime, entry: float, exit_px: float,
               qty: int, actual: Optional[float]) -> None:
    m0, m1 = _minute(first), _minute(end)
    inner = [b for b in bars if m0 < b[0] < m1]
    if not inner:
        return
    peak = max(inner, key=lambda b: b[2])
    protect = entry * (1 - STOP_SLIPPAGE_PCT)
    if peak[2] < entry * (1 + PROTECT_GAIN_PCT) or exit_px >= protect:
        return
    better = _pnl(entry, protect, qty, trade["exchange"], _orders(trade))
    item["flags"].append(_flag(
        "GAVE_BACK_PROFIT",
        f"At {_hhmm(peak[0])} the option was {_px(peak[2])}, {peak[2] / entry - 1:.0%} above your {_px(entry)} buy "
        f"(about {_rs((peak[2] - entry) * qty)} open on {qty} qty). You sold at {_px(exit_px)} at "
        f"{_hhmm(trade['last_sell_at'])}: {_rs(actual)} after charges.",
        (round(actual - better, 2) if better is not None and actual is not None else None),
        why="A trade that was well in profit ended as a loss. A bought option can give back a gain within minutes; "
            "a stop at your buy price keeps a winner from turning into a loser.",
        better=(f"Moving the SL order to your buy price once it was up {PROTECT_GAIN_PCT:.0%} would have sold near "
                f"{_px(entry)} (a fast fall fills a little lower): about {_instead(better, actual)}."),
        better_pnl=better, actual_pnl=actual))


def _stop_moves(item: dict, sl_orders: list, ctx: Context, trade: dict, bars: list, basis: Optional[str],
                first: datetime, end: datetime, closed: bool, entry: float, exit_px: Optional[float],
                qty: Optional[int], actual: Optional[float]) -> None:
    lowered, raised = [], []
    for order in sl_orders:
        for change in ctx.changes.get(order["order_id"], []):
            at = _dt(change["changed_at"])
            if change["field"] != "trigger_price" or at is None or not first <= at <= end:
                continue
            (lowered if change["new_value"] < change["old_value"] else raised).append((at, change))
    if lowered:
        lowered.sort(key=lambda pair: pair[0])
        at, change = lowered[0]
        original = change["old_value"]
        lowest = min(c["new_value"] for _, c in lowered)
        better_pnl, touch = None, None
        if closed and exit_px is not None and qty and exit_px < original:
            touch = next((b for b in bars if b[0] >= at and _inside(b, first, end, basis) and b[3] <= original),
                         None)
            if touch is not None:
                better_pnl = _pnl(entry, original, qty, trade["exchange"], _orders(trade))
        times = f" ({len(lowered)} times)" if len(lowered) > 1 else ""
        item["flags"].append(_flag(
            "STOP_LOWERED", f"You moved your SL order down from {_px(original)} to {_px(lowest)} at "
                            f"{_hhmm(at)}{times}.",
            (round(actual - better_pnl, 2) if better_pnl is not None and actual is not None else None),
            why="Lowering a stop as the price comes near it is hoping, not planning: the loss grows past the one "
                "you accepted when you placed it.",
            better=(f"Keeping it at {_px(original)}: the option traded there at {_hhmm(touch[0])}, so about "
                    f"{_instead(better_pnl, actual)}." if better_pnl is not None else
                    "Leave the stop where you placed it; move it only up, to lock in profit."),
            better_pnl=better_pnl, actual_pnl=actual if better_pnl is not None else None))
    # [O24-SR] A trailed stop is praised even after a small trim down, when it
    # ended above where it started and its last move was up (Oct 23: 33 -> 90
    # with one 68 -> 66 trim; the trade made +₹6,135).
    moves = sorted(lowered + raised, key=lambda pair: pair[0])
    trailed = bool(raised) and (not lowered or (moves[-1][1]["new_value"] > moves[-1][1]["old_value"]
                                                and moves[-1][1]["new_value"] > moves[0][1]["old_value"]))
    if trailed:
        at, change = sorted(raised, key=lambda pair: pair[0])[-1]
        item["positives"].append(_positive(
            "STOP_TRAILED", f"You raised your SL order to {_px(change['new_value'])} at {_hhmm(at)}, so less of the "
                            f"trade was at risk."))


def _price_raised(item: dict, ctx: Context, trade: dict, card: Optional[dict]) -> None:
    for fill in trade["buys"]:
        raises = [c for c in ctx.changes.get(fill.get("order_id") or "", [])
                  if c["field"] == "price" and c["new_value"] > c["old_value"]]
        if not raises:
            continue
        start, final = raises[0]["old_value"], raises[-1]["new_value"]
        total = final / start - 1 if start else 0.0
        if len(raises) < PRICE_RAISES_MIN and total < PRICE_RAISE_PCT:
            continue
        limit = (card or {}).get("buy_limit")
        tick = (card or {}).get("tick_size") or 0.05
        if limit and final <= limit + tick:
            continue   # raising inside the card's buy-up-to is following the card
        first_at, last_at = _dt(raises[0]["changed_at"]), _dt(raises[-1]["changed_at"])
        why = "Raising the price to get filled is chasing: each raise puts the stop further away and the target closer."
        if limit:
            why += f" The card's buy-up-to was {_px(limit)}."
        item["flags"].append(_flag(
            "PRICE_RAISED_TO_FILL",
            f"You raised your buy price {len(raises)} time{'s' if len(raises) != 1 else ''}, from {_px(start)} to "
            f"{_px(final)} ({_pct(total, 1)}), between {_hhmm(first_at)} and {_hhmm(last_at)}.", None,
            why=why + _worked(trade["pnl"]),
            better="Leave the order at your price. If it does not fill, the trade is gone, and that is fine."))
        return


def _held_overnight(item: dict, trade: dict, ctx: Context) -> None:
    day = trade["session_date"]
    if not trade["open_lots"] or day not in ctx.complete_days:
        return
    positions = ctx.positions.get(day)
    if positions is not None:
        held = sum(p["quantity"] for p in positions if p["exchange"] == trade["exchange"]
                   and p["tradingsymbol"] == trade.get("tradingsymbol"))
        if held <= 0:
            return   # Zerodha shows it closed (for example the broker's own square-off)
    expired = trade.get("expiry") == day
    reason = f"You still held {_lots(trade['open_lots'])} of {item.get('option')} at the close."
    if expired:
        reason += f" It expired {when(ctx, day)}."
        why = ("On expiry day an option that is not in the money at the close settles at zero; holding it to the "
               "end is a bet on the last minutes.")
    else:
        why = ("A bought option held overnight can open much lower after a gap and loses time value every day, "
               "and no card plan covers it.")
    item["flags"].append(_flag("HELD_OVERNIGHT", reason, None, why=why,
                               better="Sell before the close, by 15:15, unless you planned to hold it."))


# ---------------------------------------------------------------------------
# per day
# ---------------------------------------------------------------------------

def day_details(row: dict, ctx: Context) -> None:
    """The day's cash, orders, rejections and positions; a refused buy for
    want of money is a day lesson."""
    day = row["day"]
    cash = cash_of(ctx.accounts.get(day))
    if cash:
        pnl = row.get("actual_pnl")
        row["account"] = {"cash": round(cash, 2), "pnl_pct": round(pnl / cash, 4) if pnl is not None else None}
    orders = [o for o in ctx.orders if o["session_date"] == day]
    if orders:
        rejected = [o for o in orders if o["status"] == "REJECTED"]
        row["orders"] = {
            "placed": len(orders), "filled": sum(1 for o in orders if (o.get("filled_quantity") or 0) > 0),
            "rejected": [{"at": _hhmm(_dt(o["placed_at"])), "side": o["transaction_type"],
                          "tradingsymbol": o["tradingsymbol"], "quantity": o.get("quantity"),
                          "reason": o.get("status_message"), "plain": refusal_plain(o, orders)} for o in rejected],
            "cancelled_unfilled": sum(1 for o in orders if o["status"] == "CANCELLED"
                                      and not (o.get("filled_quantity") or 0)),
            "modified": sum(1 for o in orders if ctx.changes.get(o["order_id"])),
            "market": sum(1 for o in orders if o.get("order_type") == "MARKET"),
        }
        funds = [o for o in rejected if o["transaction_type"] == "BUY" and _FUNDS.search(o.get("status_message") or "")]
        if funds:
            first = funds[0]
            more = f" ({len(funds)} refusals {when(ctx, day)})" if len(funds) > 1 else ""
            row["day_flags"].append(_flag(
                "INSUFFICIENT_FUNDS",
                f"At {_hhmm(_dt(first['placed_at']))} Zerodha refused your buy of {first.get('quantity')} "
                f"{first['tradingsymbol']}: “{(first.get('status_message') or '')[:120]}”{more}.", None,
                why="The order was bigger than the money in the account. Sizing from the account first keeps every "
                    "order possible and every loss affordable.",
                better="Decide the lots before the trade, from the cash you have (each trade shows its risk against "
                       "your cash)."))
    positions = ctx.positions.get(day) or []
    held = [p for p in positions if p["quantity"] > 0]
    if held:
        row["open_positions"] = [{"tradingsymbol": p["tradingsymbol"], "quantity": p["quantity"],
                                  "product": p["product"], "average_price": p.get("average_price"),
                                  "last_price": p.get("last_price")} for p in held]
    carried = [p for p in positions if p["overnight_quantity"] > 0]
    if carried:
        row["carried_in"] = [{"tradingsymbol": p["tradingsymbol"], "overnight_quantity": p["overnight_quantity"]}
                             for p in carried]
