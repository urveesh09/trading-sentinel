"""[N06 2026-11-04] The Sentinel's own way of trading, told to the partner as advice. Messages only: nothing here
places, changes or cancels an order, and nothing is decided for the partner.

Owner's order (Nov 4): the partner lost Rs 51,869 in a day while the watch's messages arrived on time; make the
advice better so that "they follow the trades of the sentinel", with the Sentinel's own strategies, and "no matter
what still we will not take any action on behalf of the partner. Only advice." [N06c, Nov 4 night] "long long
paragraph with market on reading is impossible": every line here is short and concrete, or it is not sent.

What the stored days showed (Production, Oct 27 - Nov 4, read-only, partner_watch_score's frozen rule v2):
  - buys much bigger than the partner's usual share of cash: 57 trades, -Rs 38,024 (UNUSUAL_SIZE: SUPPORTED);
    the rest, 175 trades, -Rs 2,130;
  - buys within 30 minutes of a losing exit: 143 trades, -Rs 31,721 (AFTER_LOSS: SUPPORTED);
  - buys after a 20% run in 15 minutes: 96 trades, +Rs 49,703 (CHASED_SPIKE: NOT_SUPPORTED, so the check leaves
    that warning out while its verdict says so);
  - the Sentinel's own F&O paper trades on those days, one lot each: 11 trades, -Rs 7,706. Every message says it
    is paper and its record.

What the partner gets:
  - ``size_line``: the loss at the plan stop for 1 lot and for 2 lots, in rupees and as a share of the day's cash,
    and the most the Sentinel risks on a trade (``settings.FNO_MAX_RISK_PCT``, 2%). Choices, not a limit (owner:
    "we need them to have freedom");
  - after a losing trade the Sentinel's own rule (one lot, fno_n11.lot_ceiling); on adding under the first buy,
    its rule on adding (fno_n11 earned lot: only to a trade up a full stop);
  - the partner's own record on a warning, only while partner_watch_score's frozen verdict SUPPORTS it;
  - the Sentinel's own main trades as it takes them (``events``): the F&O paper main book (source FNO_PAPER) and,
    with EXPIRY_MAIN_STRATEGY "E032", the expiry book's main ticket; a buy only while it is fresh and still open.

Pure helpers and read-only readers; partner_watch sends the messages (kinds SENTINEL and SENTINEL_EXIT).
"""
from __future__ import annotations

import json
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
FRESH_BUY = timedelta(minutes=2)           # [N06c] a Sentinel buy older than this when first seen is not offered
FRESH_SELL = timedelta(minutes=30)         # a sale is told while this recent (only for a buy that was told)
MOST_LOTS = 50                             # the size search never looks past this many lots
REASONS = {
    "underlying_stop": "stop level", "premium_backstop": "25% backstop", "trail_stop": "trailing stop",
    "profit_lock": "profit lock", "time_stop": "time limit", "hard_flat_1510": "15:10 close", "target": "target",
    # the expiry ticket's own actions (expiry_e02.action, expiry_paper.manage_position)
    "STOP": "stop", "HARD_STOP": "stop", "STRUCTURE": "index stop", "TARGET": "2x target",
    "TARGET_BASE": "2x sale, the rest runs", "RUNNER_TRAIL": "runner's floor", "HERO_TARGET": "10x target",
    "TIME": "time limit", "FLAT": "15:14 sale", "TRAIL": "trailing stop",
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
# size: concrete choices in the partner's rupees
# ---------------------------------------------------------------------------

def loss_at(entry: float, stop: float, qty: int, exchange: str) -> float:
    """What ``qty`` bought at ``entry`` loses if sold at ``stop``, with that quantity's own round-trip charges."""
    return round((entry - stop) * qty + _costs(entry, stop, qty, exchange), 2)


def size_advice(entry: Optional[float], stop: Optional[float], lot: Optional[int], cash: Optional[float],
                exchange: str = "NFO", *, most: Optional[int] = None) -> Optional[dict]:
    """The loss at ``stop`` for one and for two lots (each with its own charges), and ``lots``: the most lots whose
    loss stays within ``risk_share()`` of ``cash`` (0 when one lot is already over; ``most`` caps it). None without
    a price, a stop under it, a lot size or the cash."""
    if not entry or stop is None or not lot or not cash or cash <= 0 or stop >= entry:
        return None
    budget = round(risk_share() * cash, 2)
    one, two = loss_at(entry, stop, lot, exchange), loss_at(entry, stop, 2 * lot, exchange)
    lots = 0
    for n in range(1, int(most or MOST_LOTS) + 1):
        if loss_at(entry, stop, n * lot, exchange) > budget:
            break
        lots = n
    return {"lots": lots, "lot": int(lot), "one": one, "two": two, "budget": budget, "cash": float(cash)}


def size_line(advice: Optional[dict], *, stop_name: str = "the plan stop") -> str:
    """[N06c] One line of choices: "📏 At the plan stop: 1 lot −₹2,048 (2.5%) · 2 lots −₹4,096 (5.1%). The
    Sentinel risks at most 2% (₹1,609)." "" without advice. The partner's own size is in the stop line above it."""
    if not advice:
        return ""
    cash = advice["cash"]
    return (f"📏 At {stop_name}: 1 lot −{_amt(advice['one'])} ({_share(advice['one'] / cash)}) · 2 lots "
            f"−{_amt(advice['two'])} ({_share(advice['two'] / cash)}). The Sentinel risks at most "
            f"{risk_share():.0%} ({_amt(advice['budget'])}).")


AFTER_LOSS_RULE = "The Sentinel takes 1 lot after a loss."
ADD_RULE = "The Sentinel adds only to a trade already up a full stop."


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
        _first, _last, trades = score.load(db_path, None, before)
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
    w, u = recs[warning]["warned"], recs[warning]["unwarned"]
    if warning == "UNUSUAL_SIZE":
        return (f"📊 Your oversized buys{_since(recs, warning)}: {_signed(w['total'])} ({w['n']}); usual size "
                f"{_signed(u['total'])} ({u['n']}).")
    if warning == "AFTER_LOSS":
        return f"📊 Your buys within 30 min of a loss{_since(recs, warning)}: {_signed(w['total'])} ({w['n']})."
    return ""


def record_tail(recs: dict, warning: str) -> str:
    """[N06c] The partner's own record as the end of that warning's line (" Since 27 Oct such buys: −₹38,024 (57);
    usual size −₹2,130 (175)."), while its frozen verdict supports it; "" otherwise."""
    if not supported(recs, warning):
        return ""
    w, u = recs[warning]["warned"], recs[warning]["unwarned"]
    since = _since(recs, warning).replace(" since", "Since", 1) if _since(recs, warning) else "So far"
    tail = f" {since} such buys: {_signed(w['total'])} ({w['n']})"
    if warning == "UNUSUAL_SIZE":
        tail += f"; usual size {_signed(u['total'])} ({u['n']})"
    return tail + "."


def morning_lines(recs: dict) -> list:
    """For the watch-on message: one line of the partner's supported records, and what the Sentinel will send."""
    parts = []
    if supported(recs, "UNUSUAL_SIZE"):
        w, u = recs["UNUSUAL_SIZE"]["warned"], recs["UNUSUAL_SIZE"]["unwarned"]
        parts += [f"usual size {_signed(u['total'])} ({u['n']})", f"oversized {_signed(w['total'])} ({w['n']})"]
    if supported(recs, "AFTER_LOSS"):
        w = recs["AFTER_LOSS"]["warned"]
        parts.append(f"within 30 min of a loss {_signed(w['total'])} ({w['n']})")
    since = _since(recs, "UNUSUAL_SIZE") or _since(recs, "AFTER_LOSS")
    lines = [f"📊 Your buys{since}: " + " · ".join(parts) + "."] if parts else []
    lines.append("🤖 The Sentinel's own trades (paper) come here as it takes them.")
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


def record_text(record: Optional[dict]) -> str:
    if not record:
        return "📊 Its record: no closed paper trades yet."
    return (f"📊 Its last {record['n']} paper trades: {record['won']} won, {_signed(record['per_lot'])} a lot. "
            f"It loses often.")


def fno_buy_text(trade: dict, cash: Optional[float], record: Optional[dict], exchange: str) -> str:
    """The partner's message for the Sentinel's F&O buy: four short lines."""
    name = _option_name(trade["tradingsymbol"])
    entry = float(trade["entry_premium"])
    expiry = trade.get("expiry")
    when = f" ({date.fromisoformat(str(expiry)[:10]):%d %b})" if expiry else ""
    lines = [f"🤖 Sentinel bought {name}{when} at {_px(entry)}, {_when(trade['entry_time']):%H:%M:%S} (paper)."]
    stop = option_stop(trade)
    underlying = trade.get("underlying") or ""
    bits = []
    if trade.get("stop_underlying"):
        bits.append(f"🛑 Stop {underlying} fut {float(trade['stop_underlying']):,.0f}"
                    + (f" (option ≈{_px(stop)})" if stop is not None else ""))
    elif stop is not None:
        bits.append(f"🛑 Stop option ≈{_px(stop)}")
    if trade.get("target_underlying"):
        bits.append(f"🎯 target fut {float(trade['target_underlying']):,.0f}")
    if bits:
        lines.append(" · ".join(bits) + ".")
    line = size_line(size_advice(entry, stop, trade.get("lot_size"), cash, exchange), stop_name="its stop")
    if line:
        lines.append(line)
    lines.append(record_text(record) + " Your call.")
    return "\n".join(lines)


def fno_sell_text(trade: dict) -> str:
    name = _option_name(trade["tradingsymbol"])
    lots = max(1, int(trade.get("initial_lots") or trade.get("lots") or 1))
    per_lot = float(trade.get("pnl") or 0.0) / lots
    reason = REASONS.get(str(trade.get("exit_reason") or ""), str(trade.get("exit_reason") or "exit").replace("_", " "))
    return (f"🤖 Sentinel sold {name} at {_px(float(trade['exit_premium']))}, {_hhmm(trade['exit_time'])} ({reason}): "
            f"{_signed(per_lot)} a lot (paper).")


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
    flat = (p.get("e02_policy") or {}).get("flat", "15:28")
    lines = [f"🤖 Sentinel's expiry ticket: bought {name} (expires today) at {_px(entry)}, "
             f"{_when(p['entry_ts']):%H:%M:%S} (paper)."]
    index = f" or {p.get('underlying', '')} {float(p['underlying_stop']):,.0f}" if p.get("underlying_stop") else ""
    at_two = (f"sells half at 2x ({_px(2 * entry)})" if int(p.get("lots") or 1) >= 2   # expiry_e02.entry_text
              else f"sells at 2x ({_px(2 * entry)})")
    lines.append(f"🛑 Stop {_px(float(p['stop']))}{index} · {at_two} · all from {flat}.")
    line = size_line(size_advice(entry, float(p["stop"]), lot, cash, p.get("exchange") or "NFO"), stop_name="its stop")
    if line:
        lines.append(line + f" A jump can take a lot's whole {_amt(entry * lot)}.")
    if record:
        lines.append(f"📊 Its {p.get('underlying', '')} expiry tickets: {record['n']}, {record['won']} won, "
                     f"{_signed(record['net'])}. Most lose a little; a few pay big. Your call.")
    else:
        lines.append(f"📊 Its first {p.get('underlying', '')} ticket: no record yet. Most lose a little; a few pay big. "
                     f"Your call.")
    return "\n".join(lines)


def expiry_sell_text(p: dict, event: dict) -> str:
    name = _option_name(p["symbol"])
    reason = REASONS.get(str(event.get("action") or ""), str(event.get("action") or "exit").replace("_", " ").lower())
    line = (f"🤖 Sentinel's expiry ticket: sold {_lots(int(event['lots']))} of {name} at {_px(float(event['price']))}, "
            f"{_hhmm(event['ts'])} ({reason})")
    if p.get("status") == "CLOSED":
        return line + f"; closed {_signed(float(p['net_pnl']))} (paper)."
    return line + f"; {_lots(int(p.get('lots_open') or 0))} still running (paper)."


def open_line(db_path: str, day: str, underlying: str) -> str:
    """For a check: what the Sentinel's main book holds on this index now."""
    trades = [t for t in fno_trades(db_path, day) if (t.get("underlying") or "") == underlying]
    opened = [t for t in trades if t.get("status") == "OPEN"]
    if opened:
        t = opened[-1]
        return (f"🤖 Sentinel now: holds {_option_name(t['tradingsymbol'])} (bought {_hhmm(t['entry_time'])} at "
                f"{_px(float(t['entry_premium']))}).")
    return f"🤖 Sentinel now: nothing on {underlying} ({len(trades)} trade{'s' if len(trades) != 1 else ''} today)."


def events(db_path: str, day: str, now: datetime) -> list:
    """The Sentinel's trades to tell now: [(key, kind, build, at, symbol)], ``build(cash)`` making the text.
    [N06c] A buy only while FRESH_BUY recent and still open (a trade already closed is never offered: the audit's
    case, reproduced in tests); a sale (key ``...:sell`` or the expiry event's index) while FRESH_SELL recent. The
    caller sends a sale only after its buy was told."""
    out = []
    before = day
    record = None
    for trade in fno_trades(db_path, day):
        if not trade.get("entry_time") or not trade.get("entry_premium") or not trade.get("tradingsymbol"):
            continue                  # an odd row says nothing (and never stops the others)
        entered = _when(trade["entry_time"])
        key = f"sentinel:{day}:fno:{trade['id']}"
        if trade.get("status") == "OPEN" and timedelta(0) <= now - entered <= FRESH_BUY:
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
        if p.get("status") == "OPEN" and timedelta(0) <= now - entered <= FRESH_BUY:
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
