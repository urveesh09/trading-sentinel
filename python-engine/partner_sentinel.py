"""[N06 2026-11-04] The Sentinel's own way of trading, told to the partner as advice. Messages only: nothing here
places, changes or cancels an order, and nothing is decided for the partner.

Owner's order (Nov 4): the partner lost Rs 51,869 in a day while the watch's messages arrived on time; make the
advice better so that "they follow the trades of the sentinel", with the Sentinel's own strategies, and "no matter
what still we will not take any action on behalf of the partner. Only advice."

What the stored days showed (Production, Oct 27 - Nov 4, read-only, partner_watch_score's frozen rule v2):
  - buys much bigger than the partner's usual share of cash: 57 trades, -Rs 38,024 (UNUSUAL_SIZE: SUPPORTED);
    the rest, 175 trades, -Rs 2,130: about even before the big ones;
  - buys within 30 minutes of a losing exit: 143 trades, -Rs 31,721 (AFTER_LOSS: SUPPORTED);
  - buys after a 20% run in 15 minutes: 96 trades, +Rs 49,703 (CHASED_SPIKE: NOT_SUPPORTED: the warning was wrong
    for this partner, so the check no longer raises it while its verdict says so);
  - the same trades sized by the Sentinel's rule (at most 2% of cash lost at the plan stop, at least one lot):
    -Rs 11,942 instead of -Rs 40,154, worst day -Rs 16,218 instead of -Rs 51,869. Smaller losses, not a profit.
  - the Sentinel's own F&O paper trades on those days, one lot each: 11 trades, -Rs 7,706. It is not a money
    printer either: its edge in years of replays is small and it loses on many days. Every message says so.

So the advice is the Sentinel's discipline, in the partner's own rupees:
  - the size its rule gives for a buy (``size_advice``): ``settings.FNO_MAX_RISK_PCT`` of the day's cash lost at
    the plan stop, the Sentinel's own per-trade limit. One lot that already loses more is said as such;
  - after a losing trade the Sentinel takes one lot at most for the rest of the day (fno_n11.lot_ceiling), and it
    adds lots only to a trade already up by a full stop (fno_n11 earned lot), never to a falling one;
  - the partner's own record on a warning, shown only while partner_watch_score's frozen verdict SUPPORTS it
    (``records``): their numbers, not a rule;
  - the Sentinel's own main trades as it takes them (``sentinel_trades``): the F&O paper main book (source
    FNO_PAPER, the N11 book) and, with EXPIRY_MAIN_STRATEGY "E032", the expiry book's main ticket; each with its
    stop, target, the size its rule gives the partner's cash, and its own recent record.

Pure helpers and read-only readers; partner_watch sends the messages (kinds SENTINEL and SENTINEL_EXIT).
"""
from __future__ import annotations

import json
import math
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from typing import Optional

import pytz

from config import settings

IST = pytz.timezone("Asia/Kolkata")

FNO_SOURCE = "FNO_PAPER"
EARNED_LOT = "N11_ADD"                     # the earned lot is its own position: told with its parent, not as a trade
RECORD_TRADES = 20                         # the Sentinel's record line: its last closed main-book trades
FRESH_BUY = timedelta(minutes=5)           # a Sentinel buy older than this when first seen is not offered
FRESH_SELL = timedelta(minutes=30)         # a sale is told while this recent (only for a buy that was told)
REASONS = {
    "underlying_stop": "its stop level", "premium_backstop": "its 25% backstop", "trail_stop": "its trailing stop",
    "profit_lock": "its profit lock", "time_stop": "its time limit", "hard_flat_1510": "its 15:10 close",
    "target": "its target",
    # the expiry ticket's own actions (expiry_e02.action, expiry_paper.manage_position)
    "STOP": "its stop", "HARD_STOP": "its stop", "STRUCTURE": "its index stop", "TARGET": "its target (2x)",
    "TARGET_BASE": "its 2x sale (the rest runs)", "RUNNER_TRAIL": "its runner's floor", "HERO_TARGET": "its 10x target",
    "TIME": "its time limit", "FLAT": "its 15:14 sale", "TRAIL": "its trailing stop",
}


def risk_share() -> float:
    """The Sentinel's own most-lost-per-trade share of its cash (2%)."""
    return float(settings.FNO_MAX_RISK_PCT)


def _amt(value: float) -> str:
    from partner_coach import _amt as coach_amt
    return coach_amt(value)


def _px(value: float) -> str:
    from partner_coach import _px as coach_px
    return coach_px(value)


def _signed(value: float) -> str:
    return f"{'−' if value < 0 else '+'}{_amt(value)}"


def _share(value: float) -> str:
    """A share of cash: one decimal under 10%, so a loss just over the 2% rule never reads as 2%."""
    return f"{value * 100:.1f}%" if value < 0.10 else f"{value:.0%}"


def _lots(n: int) -> str:
    return f"{n} lot{'s' if n != 1 else ''}"


def _when(value) -> datetime:
    """A stored time as an IST-aware datetime (a time stored without its zone is IST, as the engine writes it)."""
    at = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return at.astimezone(IST) if at.tzinfo else IST.localize(at)


def _hhmm(value) -> str:
    return _when(value).strftime("%H:%M")


def _costs(entry: float, exit_: float, qty: int, exchange: str) -> float:
    from partner_coach import round_trip_costs
    return round_trip_costs(entry, exit_, qty, exchange)


# ---------------------------------------------------------------------------
# size: the Sentinel's rule in the partner's rupees
# ---------------------------------------------------------------------------

def size_advice(entry: Optional[float], stop: Optional[float], lot: Optional[int], cash: Optional[float],
                exchange: str = "NFO", *, most: Optional[int] = None) -> Optional[dict]:
    """The lots the Sentinel's rule allows for a buy at ``entry`` with its stop at ``stop``: at most ``risk_share()``
    of ``cash`` lost at the stop, charges included; ``most`` caps it (the Sentinel's own lots on its own trade).
    ``lots`` 0: even one lot loses more. None without a price, a stop under it, a lot size or the cash."""
    if not entry or stop is None or not lot or not cash or cash <= 0 or stop >= entry:
        return None
    per_lot = round((entry - stop) * lot + _costs(entry, stop, lot, exchange), 2)
    budget = round(risk_share() * cash, 2)
    lots = int(budget // per_lot) if per_lot > 0 else 0
    if most is not None:
        lots = min(lots, int(most))
    return {"lots": lots, "lot": int(lot), "per_lot": per_lot, "budget": budget, "cash": float(cash),
            "share": per_lot / cash}


def usual_lots(entry: Optional[float], lot: Optional[int], cash: Optional[float], usual: Optional[float]) -> Optional[int]:
    """[N06b] The lots the partner's own usual share of cash buys at ``entry`` (at least one); None without a usual."""
    if not entry or not lot or not cash or not usual or usual <= 0:
        return None
    return max(1, int((usual * cash) // (entry * lot)))


def _sentinel_part(advice: dict) -> str:
    rule = f"The Sentinel's own rule (at most {risk_share():.0%} of cash lost at the stop)"
    if advice["lots"] >= 1:
        return f"{rule} would take {_lots(advice['lots'])}."
    return f"{rule} would take less than one lot here: one lot is {_share(advice['share'])} of your cash at the stop."


def size_line(advice: Optional[dict], *, usual: Optional[float] = None, entry: Optional[float] = None,
              bought_lots: Optional[int] = None, stop_name: str = "the plan stop", verb: str = "bought") -> str:
    """One line on size; "" without advice. [N06b, owner: "don't do extreme conservative, we need them to have
    freedom"] It leads with the partner's own usual size (``usual``, their share of cash; their usual-size buys
    were about even, Oct 27 - Nov 4) and what that loses at the stop, then the Sentinel's own 2% rule as a
    reference. ``bought_lots`` over the usual is said ("You bought 5 lots", for a check "You asked about 5 lots")."""
    if not advice:
        return ""
    n = usual_lots(entry, advice["lot"], advice["cash"], usual)
    if n is not None:
        line = (f"📏 Your usual size here: about {_lots(n)} ({n * advice['lot']}), {usual:.0%} of your cash; at "
                f"{stop_name} about −{_amt(n * advice['per_lot'])} ({_share(n * advice['share'])} of your cash). "
                + _sentinel_part(advice))
        more = bought_lots is not None and bought_lots > n
    else:
        line = (f"📏 One lot ({advice['lot']}) loses about {_amt(advice['per_lot'])} at {stop_name}, "
                f"{_share(advice['share'])} of your cash. " + _sentinel_part(advice))
        more = bought_lots is not None and bought_lots > max(1, advice["lots"])
    if more:
        line += f" You {verb} {_lots(bought_lots)}."
    return line


def follow_line(advice: Optional[dict]) -> str:
    """For one of the Sentinel's own trades: what a lot loses at its stop for the partner's cash, and the lots its
    rule would take; "" without advice. The numbers, not a limit: how many to take is the partner's call."""
    if not advice:
        return ""
    line = (f"📏 For your {_amt(advice['cash'])} cash: each lot ({advice['lot']}) loses about "
            f"{_amt(advice['per_lot'])} at its stop, {_share(advice['share'])} of your cash. ")
    if advice["lots"] >= 1:
        return line + f"Its own rule would take {_lots(advice['lots'])} for you."
    return line + f"Its own rule ({risk_share():.0%} a trade) would take less than one lot for you."


AFTER_LOSS_RULE = "After a losing trade the Sentinel itself takes one lot at most for the rest of the day."
ADD_RULE = "The Sentinel adds a lot only to a trade already up by a full stop, never to a falling one."


# ---------------------------------------------------------------------------
# the partner's own record on the warnings the frozen score supports
# ---------------------------------------------------------------------------

_RECORDS: dict = {}                         # (db_path, day) -> records, worked out once a day


def records(db_path: str, day: str) -> dict:
    """{warning: {"verdict", "warned", "unwarned", "since"}} from partner_watch_score (its frozen rule) on the
    stored days before ``day``; {} when nothing is stored. Read-only, cached for the day."""
    key = (db_path, day)
    if key in _RECORDS:
        return _RECORDS[key]
    import partner_watch_score as score
    try:
        before = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
        first, _last, trades = score.load(db_path, None, before)
        scored = score.score(trades) if trades else {"warnings": {}, "days": []}
    except (sqlite3.Error, ValueError):
        scored = {"warnings": {}, "days": []}
    since = scored["days"][0] if scored.get("days") else None
    out = {name: {**data, "since": since} for name, data in scored["warnings"].items()}
    _RECORDS[key] = out
    return out


def supported(recs: dict, warning: str) -> bool:
    return (recs.get(warning) or {}).get("verdict") == "SUPPORTED"


def refuted(recs: dict, warning: str) -> bool:
    """The frozen score says this warning does not pick out losing trades (NOT_SUPPORTED)."""
    return (recs.get(warning) or {}).get("verdict") == "NOT_SUPPORTED"


def _since(recs: dict, warning: str) -> str:
    since = (recs.get(warning) or {}).get("since")
    return f" since {date.fromisoformat(since):%d %b}" if since else ""


def record_line(recs: dict, warning: str) -> str:
    """The partner's own numbers on one warning, while its frozen verdict supports it; "" otherwise."""
    if not supported(recs, warning):
        return ""
    data = recs[warning]
    w, u = data["warned"], data["unwarned"]
    if warning == "UNUSUAL_SIZE":
        return (f"📊 Your record{_since(recs, warning)}: buys much bigger than your usual, {w['n']} trades, "
                f"{_signed(w['total'])}; your usual size, {u['n']} trades, {_signed(u['total'])}.")
    if warning == "AFTER_LOSS":
        return (f"📊 Your record{_since(recs, warning)}: buys within 30 min of a losing exit, {w['n']} trades, "
                f"{_signed(w['total'])}; your other buys, {u['n']} trades, {_signed(u['total'])}.")
    return ""


def morning_lines(recs: dict) -> list:
    """For the watch-on message: the partner's supported records, then what the Sentinel will send."""
    lines = [line for line in (record_line(recs, "UNUSUAL_SIZE"), record_line(recs, "AFTER_LOSS")) if line]
    lines.append(f"🤖 The Sentinel's own trades come here as it takes them (paper; usually 0–3 a day), with the size "
                 f"its rule gives your cash: at most {risk_share():.0%} of it lost at the stop. Each plan below also "
                 f"says the Sentinel's size. It can lose too: following it is your call.")
    return lines


# ---------------------------------------------------------------------------
# the Sentinel's own main trades (read-only)
# ---------------------------------------------------------------------------

_FNO_COLS = ("id", "tradingsymbol", "underlying", "expiry", "opt_type", "lots", "lot_size", "initial_lots", "qty",
             "entry_time", "entry_premium", "entry_underlying", "stop_underlying", "target_underlying",
             "premium_stop", "delta_at_entry", "status", "exit_time", "exit_premium", "exit_reason", "pnl",
             "strategy")


def _ro(path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1)


def option_stop(trade: dict) -> Optional[float]:
    """The option price where the Sentinel's F&O trade is expected to be sold: the higher of its stop level priced
    by the entry delta and its premium backstop (whichever it reaches first, the way it plans its own risk)."""
    entry = trade.get("entry_premium")
    if not entry:
        return None
    levels = []
    delta, u_entry, u_stop = trade.get("delta_at_entry"), trade.get("entry_underlying"), trade.get("stop_underlying")
    if delta and u_entry and u_stop:
        levels.append(entry - abs(float(delta)) * abs(float(u_entry) - float(u_stop)))
    if trade.get("premium_stop"):
        levels.append(float(trade["premium_stop"]))
    levels = [v for v in levels if 0 < v < entry]
    return round(max(levels), 2) if levels else None


def fno_trades(db_path: str, day: str) -> list:
    """The F&O paper main book's trades entered on ``day`` (oldest first), the earned lot left out."""
    try:
        with closing(_ro(db_path)) as db:
            rows = db.execute(f"SELECT {', '.join(_FNO_COLS)} FROM fno_positions WHERE source=? AND entry_date=? "
                              "AND COALESCE(strategy,'')<>? ORDER BY entry_time, id", (FNO_SOURCE, day, EARNED_LOT)
                              ).fetchall()
    except sqlite3.Error:
        return []
    return [dict(zip(_FNO_COLS, row)) for row in rows]


def fno_record(db_path: str, before: str, n: int = RECORD_TRADES) -> Optional[dict]:
    """The main book's last ``n`` closed trades exited before ``before`` (ISO date): count, won, and the result
    per lot after charges. None without any."""
    try:
        with closing(_ro(db_path)) as db:
            rows = db.execute("SELECT pnl, COALESCE(initial_lots, lots, 1) FROM fno_positions WHERE source=? AND "
                              "status='CLOSED' AND pnl IS NOT NULL AND exit_date<? AND COALESCE(strategy,'')<>? "
                              "ORDER BY exit_time DESC, id DESC LIMIT ?", (FNO_SOURCE, before, EARNED_LOT, n)
                              ).fetchall()
    except sqlite3.Error:
        return None
    if not rows:
        return None
    per_lot = [float(pnl) / max(1, int(lots or 1)) for pnl, lots in rows]
    return {"n": len(per_lot), "won": sum(v > 0 for v in per_lot), "per_lot": round(sum(per_lot), 2)}


def expiry_trades(db_path: str, day: str) -> list:
    """The expiry book's main ticket (E03.2) positions of ``day`` while it is the main; [] otherwise."""
    if str(getattr(settings, "EXPIRY_MAIN_STRATEGY", "")) != "E032":
        return []
    try:
        import expiry_e02
        return [p for p in expiry_e02.positions(db_path, expiry_e02.E032) if p.get("day") == day]
    except (sqlite3.Error, ValueError, KeyError, OSError):
        return []


def _option_name(symbol: str) -> str:
    import partner_broker_sync as zerodha
    parsed = zerodha.parse_option_symbol(symbol)
    if parsed is None:
        return symbol
    return f"{parsed['underlying']} {parsed['strike']:g} {parsed['opt_type']}"


def _future_name(underlying: str) -> str:
    return f"{underlying} future"


def record_text(record: Optional[dict]) -> str:
    if not record:
        return "It has no closed paper trades to show yet."
    return (f"Its last {record['n']} paper trades: {record['won']} won, {_signed(record['per_lot'])} a lot after "
            f"charges. It loses on many days; its edge in years of replays is small.")


def fno_buy_text(trade: dict, cash: Optional[float], record: Optional[dict], exchange: str) -> str:
    """The partner's message for the Sentinel's F&O buy."""
    name = _option_name(trade["tradingsymbol"])
    entry = float(trade["entry_premium"])
    expiry = trade.get("expiry")
    when = f" ({date.fromisoformat(str(expiry)[:10]):%d %b})" if expiry else ""
    lines = [f"🤖 The Sentinel's own trade (paper, not a tip): bought {name}{when} at {_px(entry)} at "
             f"{_hhmm(trade['entry_time'])}."]
    stop = option_stop(trade)
    future = _future_name(trade.get("underlying") or "")
    stop_bits = []
    if trade.get("stop_underlying"):
        stop_bits.append(f"{future} {float(trade['stop_underlying']):,.0f}")
    if stop is not None:
        stop_bits.append(f"about {_px(stop)} on the option")
    target = (f" 🎯 Its target: {future} {float(trade['target_underlying']):,.0f}."
              if trade.get("target_underlying") else "")
    lines.append(f"🛑 Its stop: {', '.join(stop_bits) or 'not known'}.{target}")
    line = follow_line(size_advice(entry, stop, trade.get("lot_size"), cash, exchange))
    if line:
        lines.append(line)
    lines.append(f"📊 {record_text(record)}")
    lines.append("I'll tell you when it sells. Whether to follow is your call.")
    return "\n".join(lines)


def fno_sell_text(trade: dict, held_qty: int = 0) -> str:
    name = _option_name(trade["tradingsymbol"])
    lots = max(1, int(trade.get("initial_lots") or trade.get("lots") or 1))
    per_lot = float(trade.get("pnl") or 0.0) / lots
    reason = REASONS.get(str(trade.get("exit_reason") or ""), str(trade.get("exit_reason") or "its exit").replace("_", " "))
    line = (f"🤖 The Sentinel sold its {name} at {_px(float(trade['exit_premium']))} at {_hhmm(trade['exit_time'])} "
            f"({reason}): {_signed(per_lot)} a lot after charges (paper).")
    if held_qty:
        line += f" You still hold {held_qty} of it."
    return line


def expiry_record(db_path: str, before: str, underlying: str) -> Optional[dict]:
    """The main ticket's closed tickets on ``underlying`` before ``before``: count, won, net."""
    try:
        import expiry_e02
        rows = [p for p in expiry_e02.positions(db_path, expiry_e02.E032)
                if p.get("status") == "CLOSED" and p.get("day", "") < before
                and p.get("underlying", "NIFTY") == underlying]
    except (sqlite3.Error, ValueError, KeyError, OSError):
        return None
    if not rows:
        return None
    return {"n": len(rows), "won": sum(p["net_pnl"] > 0 for p in rows), "net": round(sum(p["net_pnl"] for p in rows), 2)}


def expiry_buy_text(p: dict, cash: Optional[float], record: Optional[dict]) -> str:
    name = _option_name(p["symbol"])
    entry, lot = float(p["entry_price"]), int(p["lot_size"])
    policy = p.get("e02_policy") or {}
    flat = policy.get("flat", "15:28")
    lines = [f"🤖 The Sentinel's expiry ticket (paper, not a tip): bought {name} (expires today) at {_px(entry)} at "
             f"{_hhmm(p['entry_ts'])}."]
    index = (f" or {p.get('underlying', '')} {float(p['underlying_stop']):,.0f}" if p.get("underlying_stop") else "")
    lines.append(f"🛑 Its stop {_px(float(p['stop']))}{index}. At 2x ({_px(2 * entry)}) it sells part and lets the "
                 f"rest run; it sells everything from {flat}.")
    line = follow_line(size_advice(entry, float(p["stop"]), lot, cash, p.get("exchange") or "NFO", most=int(p["lots"])))
    if line:
        lines.append(line + f" If the price jumps through the stop, a lot can lose all of its {_amt(entry * lot)}.")
    if record:
        lines.append(f"📊 Its {p.get('underlying', '')} expiry tickets so far: {record['n']}, {record['won']} won, "
                     f"{_signed(record['net'])}.")
    else:
        lines.append(f"📊 Its first {p.get('underlying', '')} expiry ticket on paper: no record yet.")
    lines.append("An expiry ticket loses its small stake on most days and pays several times it on a few. "
                 "Whether to follow is your call.")
    return "\n".join(lines)


def expiry_sell_text(p: dict, event: dict) -> str:
    name = _option_name(p["symbol"])
    reason = REASONS.get(str(event.get("action") or ""), str(event.get("action") or "its exit").replace("_", " ").lower())
    line = (f"🤖 The Sentinel's expiry ticket: sold {_lots(int(event['lots']))} of {name} at "
            f"{_px(float(event['price']))} at {_hhmm(event['ts'])} ({reason})")
    if p.get("status") == "CLOSED":
        line += f"; the ticket closed {_signed(float(p['net_pnl']))} after charges (paper)."
    else:
        line += f"; {_lots(int(p.get('lots_open') or 0))} still running (paper)."
    return line


def open_line(db_path: str, day: str, underlying: str) -> str:
    """For a check: what the Sentinel's main book holds on this index now ("" when nothing is known)."""
    trades = [t for t in fno_trades(db_path, day) if (t.get("underlying") or "") == underlying]
    opened = [t for t in trades if t.get("status") == "OPEN"]
    if opened:
        t = opened[-1]
        return (f"🤖 The Sentinel now holds {_option_name(t['tradingsymbol'])} (paper, bought "
                f"{_hhmm(t['entry_time'])} at {_px(float(t['entry_premium']))}).")
    return f"🤖 The Sentinel holds nothing on {underlying} now ({len(trades)} trade{'s' if len(trades) != 1 else ''} today)."


def events(db_path: str, day: str, now: datetime) -> list:
    """The Sentinel's trades to tell now: [(key, kind, build, at, symbol)], ``build(cash)`` making the text. Buys only
    while FRESH_BUY recent; a sale (key ``...:sell`` or the expiry event's index) for any buy, while FRESH_SELL
    recent. The caller sends a sale only after its buy was told."""
    out = []
    before = day
    record = None
    for trade in fno_trades(db_path, day):
        if not trade.get("entry_time") or not trade.get("entry_premium") or not trade.get("tradingsymbol"):
            continue                  # an odd row says nothing (and never stops the others)
        entered = _when(trade["entry_time"])
        key = f"sentinel:{day}:fno:{trade['id']}"
        if timedelta(0) <= now - entered <= FRESH_BUY:
            if record is None:
                record = fno_record(db_path, before) or {}
            exchange = "BFO" if str(trade["tradingsymbol"]).startswith("SENSEX") else "NFO"
            out.append((f"{key}:buy", "SENTINEL",
                        (lambda cash, t=trade, r=record, x=exchange: fno_buy_text(t, cash, r or None, x)), entered,
                        trade["tradingsymbol"]))
        if trade.get("status") == "CLOSED" and trade.get("exit_time") and trade.get("exit_premium") is not None:
            left = _when(trade["exit_time"])
            if timedelta(0) <= now - left <= FRESH_SELL:
                out.append((f"{key}:sell", "SENTINEL_EXIT", (lambda cash, t=trade: fno_sell_text(t)), left,
                            trade["tradingsymbol"]))
    for p in expiry_trades(db_path, day):
        if not p.get("entry_ts") or not p.get("entry_price") or not p.get("symbol") or not p.get("lot_size"):
            continue
        key = f"sentinel:{day}:exp:{p.get('id')}"
        entered = _when(p["entry_ts"])
        if timedelta(0) <= now - entered <= FRESH_BUY:
            rec = expiry_record(db_path, before, p.get("underlying", "NIFTY"))
            out.append((f"{key}:buy", "SENTINEL", (lambda cash, q=p, r=rec: expiry_buy_text(q, cash, r)), entered,
                        p["symbol"]))
        for i, event in enumerate(p.get("_events") or []):
            if i == 0 or event.get("price") is None or not event.get("ts"):
                continue
            left = _when(event["ts"])
            if timedelta(0) <= now - left <= FRESH_SELL:
                out.append((f"{key}:sell:{i}", "SENTINEL_EXIT", (lambda cash, q=p, e=event: expiry_sell_text(q, e)),
                            left, p["symbol"]))
    return out


def is_sale(key: str) -> bool:
    return ":sell" in key


def buy_key(key: str) -> str:
    """The buy message a sale belongs to."""
    return key.split(":sell", 1)[0] + ":buy"
