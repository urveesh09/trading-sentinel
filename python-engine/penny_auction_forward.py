"""Funded, clock-bound Penny auction paper comparisons. Never places orders.

All auction entries and exits are capacity assumptions, actual_fill UNKNOWN.
Missing evidence keeps cash reserved and makes complete modeled P&L unavailable.
Legacy Smart/overnight stores are neither read as fills nor mutated.
"""
from __future__ import annotations

from contextlib import contextmanager, closing
from datetime import datetime, time
import json
import logging
import math
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from config import settings

IST = ZoneInfo("Asia/Kolkata")
SMART = ("SMART_OPEN_CLOSE", "SMART_OPEN_MORNING")
OVERNIGHT = ("OVERNIGHT_V2", "OVERNIGHT_V3")
WINDOWS = {
    "EXIT_INTENTS": (time(9, 0), time(9, 5)),
    "MATCH": (time(9, 12), time(9, 14)),
    "MORNING": (time(9, 30), time(15, 20)),
    "POST_BASE": (time(15, 51), time(15, 52)),
    "POST_END": (time(16, 3), time(16, 5)),
}
logger = logging.getLogger(__name__)


def enabled():
    return bool(settings.PENNY_AUCTION_FORWARD_ENABLED)


def store_path(cache):
    return str(cache) + ".penny-auction-forward.db"


def stamp(value):
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        return parsed.replace(tzinfo=IST) if parsed.tzinfo is None else parsed.astimezone(IST)
    except (TypeError, ValueError):
        return None


def positive(value):
    try:
        return not isinstance(value, bool) and math.isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError):
        return False


def dump(value):
    """Preserve invalid raw observations without emitting nonstandard JSON numbers."""
    def safe(item):
        if isinstance(item, dict):
            return {str(k): safe(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [safe(v) for v in item]
        if isinstance(item, float) and not math.isfinite(item):
            return str(item)
        return item
    return json.dumps(safe(value), default=str, allow_nan=False)


def quality(q, at, *, trade_window=None):
    provider = stamp(q.get("timestamp"))
    if not provider or provider.date() != at.date():
        return "missing_or_cross_date_provider"
    if not 0 <= (at - provider).total_seconds() <= 30:
        return "stale_or_future_provider"
    if trade_window:
        trade = stamp(q.get("last_trade_time"))
        if (not trade or trade.date() != at.date() or trade > provider
                or not trade_window[0] <= trade.time() < trade_window[1]):
            return "no_supported_session_trade"
    return None


@contextmanager
def store(cache):
    with closing(sqlite3.connect(store_path(cache), timeout=10)) as c:
        c.execute("CREATE TABLE IF NOT EXISTS rows (variant TEXT, day TEXT, ticker TEXT, payload TEXT, "
                  "PRIMARY KEY(variant,day,ticker))")
        c.execute("CREATE TABLE IF NOT EXISTS sources (family TEXT, day TEXT, payload TEXT, PRIMARY KEY(family,day))")
        c.execute("CREATE TABLE IF NOT EXISTS runs (day TEXT, phase TEXT, payload TEXT, PRIMARY KEY(day,phase))")
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise


def rows(c):
    return [json.loads(r[0]) for r in c.execute("SELECT payload FROM rows ORDER BY day,variant,ticker")]


def save(c, row):
    c.execute("INSERT OR REPLACE INTO rows VALUES(?,?,?,?)",
              (row["variant"], row["day"], row["ticker"], dump(row)))


def allocation(variant):
    return float(settings.PENNY_SMART_V3_BANKROLL if variant in SMART else settings.EDGE_OVERNIGHT_PAPER_BANKROLL)


def free_cash(c, variant):
    held = [r for r in rows(c) if r["variant"] == variant]
    initial = held[0]["initial_capital"] if held else allocation(variant)
    realized = sum(r.get("net", 0.) for r in held if r["status"] == "CLOSED")
    reserved = sum(r["reserve"] for r in held if r["status"] in ("PENDING", "OPEN", "UNRESOLVED"))
    return max(0., min(initial, initial + realized) - reserved)


def cost_rates():
    keys = ("BROKERAGE_PCT", "BROKERAGE_MAX", "EXCHANGE_PCT", "SEBI_PCT", "IPFT_PCT", "GST_PCT",
            "STAMP_DUTY_PCT", "CNC_STAMP_DUTY_PCT", "STT_MIS", "STT_CNC", "CNC_DP_CHARGE")
    rates = {"PENNY_" + k: float(getattr(settings, "PENNY_" + k)) for k in keys}
    if any(not math.isfinite(v) or v < 0 for v in rates.values()):
        raise ValueError("invalid cost schedule")
    return rates


def fees(entry, exit_price, qty, intraday, rates=None):
    from penny_risk import calc_penny_costs
    return float(calc_penny_costs(entry, exit_price, qty, is_intraday=intraday,
                                 rates=rates or cost_rates(), honor_bypass=False))


def funded_quantity(cash, limit, *, intraday, rates=None):
    """Reserve premium and a complete flat roundtrip cost before the auction."""
    if not positive(cash) or not positive(limit):
        return 0, 0.
    qty = int(cash // limit)
    while qty > 0:
        # A missed same-day sale may become delivery. Fund its charges too.
        reserve = qty * limit + max(fees(limit, limit, qty, intraday, rates), fees(limit, limit, qty, False, rates))
        if reserve <= cash:
            return qty, reserve
        qty -= 1
    return 0, 0.


def intent(variant, ticker, at, limit, qty, reserve, **extra):
    return dict(variant=variant, ticker=ticker, day=at.date().isoformat(),
                intent_at=at.isoformat(), limit=limit, order_quantity=qty, reserve=reserve,
                initial_capital=allocation(variant), cost_rates=cost_rates(),
                status="PENDING", actual_fill="UNKNOWN", **extra)


def capture_smart(cache, quotes, medians, thin, at):
    """Reuse actual 09:07 inputs, with funded identical orders in both exit arms."""
    if not enabled() or not settings.PENNY_SMART_V3_ENABLED:
        return
    at = stamp(at)
    if not at or not time(9, 0) <= at.time() < time(9, 8):
        return
    from penny_smart_v3 import _candidates, select
    day = at.date().isoformat()
    good = {t: q for t, q in quotes.items() if quality(q, at) is None}
    with store(cache) as c:
        if c.execute("SELECT 1 FROM sources WHERE family='SMART' AND day=?", (day,)).fetchone():
            return
        cash = min(free_cash(c, v) for v in SMART)
        if any(r["variant"] in SMART and r["status"] in ("PENDING", "OPEN", "UNRESOLVED") for r in rows(c)):
            cash = 0.
        picks, refused = select(_candidates(good, medians, "last_price"), capital=cash, thin=thin)
        made = []
        for pick in picks:
            # Buy limit rounded down to a valid five-paise tick, never rounded up beyond funding.
            limit = round(math.floor(pick.price * 1.01 / .05 + 1e-9) * .05, 2)
            qty, reserve = funded_quantity(cash, limit, intraday=True)
            if qty:
                for variant in SMART:
                    save(c, intent(variant, pick.ticker, at, limit, qty, reserve,
                                   prev_close=pick.prev_close, decision_quote=good[pick.ticker],
                                   entry_model="10pct_observed_auction_volume"))
                made.append(pick.ticker)
        c.execute("INSERT INTO sources VALUES('SMART',?,?)", (day, dump({
            "at": at.isoformat(), "requested": len(quotes), "fresh": len(good),
            "picks": made, "refusals": refused, "paired_available_cash": cash,
            "quotes": quotes, "medians": medians, "thin": thin})))


def capture_overnight(cache, *, day, decided, picks, nights, features, fillers, late):
    """Freeze the actual ranked 15:20 inputs, including V3 fillers, before outcomes."""
    if not enabled() or not settings.EDGE_OVERNIGHT_PAPER_ENABLED:
        return
    from edge_overnight_paper import _at_hi20
    at = stamp(decided)
    if late or not at or at.date().isoformat() != day or not time(15, 20) <= at.time() < time(15, 29):
        return
    base = [p.ticker for p in picks[:10] if positive((nights or {}).get(p.ticker))
            and nights[p.ticker] >= .001]
    high_first = sorted(base, key=lambda t: not _at_hi20((features or {}).get(t)))
    taken = {p.ticker for p in picks}
    extra = [f.ticker for f in (fillers or []) if f.ticker not in taken][:10]
    payload = {"at": at.isoformat(), "OVERNIGHT_V2": base, "OVERNIGHT_V3": high_first + extra,
               "v3_inputs_complete": features is not None, "night_means": nights,
               "features": {t: (features or {}).get(t) for t in set(base + extra)}}
    with store(cache) as c:
        c.execute("INSERT OR IGNORE INTO sources VALUES('OVERNIGHT',?,?)", (day, dump(payload)))


def bid_price(q, qty, at):
    if quality(q, at, trade_window=(time(9, 15), time(15, 30))):
        return None
    buys = (q.get("depth") or {}).get("buy") or []
    sells = (q.get("depth") or {}).get("sell") or []
    levels = [(float(x["price"]), int(x["quantity"])) for x in buys
              if positive(x.get("price")) and positive(x.get("quantity"))]
    if not levels or (sells and any(positive(x.get("price")) and float(x["price"]) < max(p for p, _ in levels)
                                    for x in sells)):
        return None
    value, left = 0., qty
    for price, quantity in sorted(levels, reverse=True):
        take = min(left, quantity)
        value += price * take
        left -= take
        if left == 0:
            return value / qty
    return None


def close_row(r, price, at, basis):
    qty = r["modeled_quantity"]
    intraday = r["variant"] in SMART and r["day"] == at.date().isoformat()
    cost = fees(r["entry_price"], price, qty, intraday, r["cost_rates"])
    r.update(status="CLOSED", exit_price=price, exit_at=at.isoformat(), exit_basis=basis,
             costs=cost, net=(price - r["entry_price"]) * qty - cost)


def _modeled_entry(r, price, volume, share):
    """Order quantity is immutable. Partial modeled shares never enlarge it."""
    qty = min(r["order_quantity"], int(float(volume) * share))
    if qty < 1 or qty < .25 * r["order_quantity"]:
        r.update(status="REFUSED", reason="below_capacity_model_minimum")
    else:
        r.update(status="OPEN", entry_price=price, modeled_quantity=qty)


def apply_phase(c, phase, quotes, at):
    """One observed batch. Uses no prices or volumes outside its declared phase."""
    if phase not in WINDOWS or not WINDOWS[phase][0] <= at.time() < WINDOWS[phase][1]:
        raise ValueError("outside phase window")
    day = at.date().isoformat()
    if phase == "POST_BASE":
        source = (c.execute("SELECT payload FROM sources WHERE family='OVERNIGHT' AND day=?", (day,)).fetchone()
                  if settings.EDGE_OVERNIGHT_PAPER_ENABLED else None)
        if source:
            source = json.loads(source[0])
            for variant in OVERNIGHT:
                if variant == "OVERNIGHT_V3" and not source["v3_inputs_complete"]:
                    continue
                existing = [r for r in rows(c) if r["variant"] == variant
                            and (r["day"] == day or r["status"] in ("PENDING", "OPEN", "UNRESOLVED"))]
                slots = 2 - len(existing)
                cash = free_cash(c, variant)
                ticket = cash / slots if slots > 0 else 0.
                for ticker in source[variant]:
                    if slots < 1 or any(r["ticker"] == ticker for r in existing):
                        continue
                    q = quotes.get(ticker) or {}
                    if (quality(q, at, trade_window=(time(15, 50), time(16)))
                            or not positive(q.get("last_price")) or not positive(q.get("volume"))):
                        continue
                    price = float(q["last_price"])
                    qty, reserve = funded_quantity(min(ticket, cash), price, intraday=False)
                    if qty:
                        r = intent(variant, ticker, at, price, qty, reserve,
                                   base_volume=float(q["volume"]), decision_quote=q,
                                   entry_model="1pct_later_postclose_volume")
                        save(c, r)
                        existing.append(r)
                        cash -= reserve
                        slots -= 1
    for r in rows(c):
        q = quotes.get(r["ticker"]) or {}
        if phase == "EXIT_INTENTS" and r["status"] == "OPEN" and r["variant"] in OVERNIGHT and r["day"] < day:
            r["auction_exit_intent_at"] = at.isoformat()
        elif phase == "MATCH":
            why = quality(q, at, trade_window=(time(9, 10), time(9, 12, 1)))
            opening = (q.get("ohlc") or {}).get("open")
            usable = not why and positive(opening) and positive(q.get("volume"))
            if r["variant"] in SMART and r["day"] == day and r["status"] == "PENDING":
                if not usable:
                    r.update(status="UNRESOLVED", reason=why or "missing_auction_price_or_volume")
                elif opening > r["limit"]:
                    r.update(status="REFUSED", reason="open_above_frozen_limit")
                else:
                    _modeled_entry(r, float(opening), q["volume"], .10)
            elif r["variant"] in OVERNIGHT and r["day"] < day and r["status"] == "OPEN":
                intended = stamp(r.get("auction_exit_intent_at"))
                if usable and intended and intended.date() == at.date() and float(q["volume"]) * .10 >= r["modeled_quantity"]:
                    close_row(r, float(opening) * .9995, at, "AUCTION_CAPACITY_MODEL")
        elif phase == "MORNING" and r["status"] == "OPEN":
            due = r["day"] < day or r["variant"] == SMART[1]
            price = bid_price(q, r["modeled_quantity"], at) if due else None
            if price is not None:
                close_row(r, price, at, "OBSERVED_BID_CAPACITY_MODEL")
        elif phase == "POST_BASE" and r["variant"] == SMART[0] and r["day"] == day and r["status"] == "OPEN":
            if (not quality(q, at, trade_window=(time(15, 50), time(16)))
                    and positive(q.get("last_price")) and positive(q.get("volume"))):
                r["close_intent"] = {"at": at.isoformat(), "price": float(q["last_price"]), "volume": float(q["volume"])}
        elif phase == "POST_END" and r["day"] == day:
            base = r.get("close_intent") if r["variant"] in SMART else {
                "at": r["intent_at"], "price": r["limit"], "volume": r.get("base_volume")}
            if not base or r["status"] not in ("PENDING", "OPEN"):
                continue
            why = quality(q, at, trade_window=(time(15, 50), time(16)))
            trade = stamp(q.get("last_trade_time"))
            good = (not why and positive(q.get("volume")) and positive(q.get("last_price"))
                    and trade > stamp(base["at"]) and abs(float(q["last_price"]) - base["price"]) < .0001
                    and float(q["volume"]) >= base["volume"])
            volume = float(q["volume"]) - base["volume"] if good else 0.
            if r["variant"] in OVERNIGHT and r["status"] == "PENDING":
                if good:
                    _modeled_entry(r, r["limit"], volume, .01)
                else:
                    r.update(status="UNRESOLVED", reason=why or "unverified_later_postclose_volume")
            elif r["variant"] == SMART[0] and good and volume * .01 >= r["modeled_quantity"]:
                close_row(r, base["price"], at, "POSTCLOSE_CAPACITY_MODEL")
        save(c, r)


async def collect(kite, phase, cache=None, now=None):
    """Bounded quote batch, calendar-gated by caller, never an order request."""
    if not enabled():
        return {"status": "disabled"}
    if phase not in WINDOWS:
        raise ValueError("unknown forward phase")
    at = stamp(now or datetime.now(IST))
    start, end = WINDOWS[phase]
    if not start <= at.time() < end:
        return {"status": "outside_window"}
    cache = cache or settings.DB_PATH
    day = at.date().isoformat()
    key = phase + ("_" + at.strftime("%H%M") if phase == "MORNING" else "")
    with store(cache) as c:
        if c.execute("SELECT 1 FROM runs WHERE day=? AND phase=?", (day, key)).fetchone():
            return {"status": "repeat"}
        records = rows(c)
        if phase == "MORNING":
            names = {r["ticker"] for r in records if r["status"] == "OPEN"
                     and (r["day"] < day or r["variant"] == SMART[1])}
            if not names:
                return {"status": "idle"}
        else:
            names = {r["ticker"] for r in records if r["status"] in ("PENDING", "OPEN", "UNRESOLVED")}
        if phase == "POST_BASE":
            source = c.execute("SELECT payload FROM sources WHERE family='OVERNIGHT' AND day=?", (day,)).fetchone()
            if source:
                s = json.loads(source[0])
                names.update(s[OVERNIGHT[0]] + s[OVERNIGHT[1]])
    error = None
    try:
        from edge_overnight_paper import _quotes
        quotes = await _quotes(kite, sorted(names)) if names and phase != "EXIT_INTENTS" else {}
    except Exception as exc:
        quotes, error = {}, type(exc).__name__
    received = stamp(now) if now is not None else datetime.now(IST)
    if received.date() != at.date() or not start <= received.time() < end:
        return {"status": "quote_crossed_deadline"}
    with store(cache) as c:
        if c.execute("SELECT 1 FROM runs WHERE day=? AND phase=?", (day, key)).fetchone():
            return {"status": "repeat"}
        apply_phase(c, phase, quotes, received)
        result = {"status": "observed", "at": received.isoformat(), "phase": phase,
                  "requested": len(names), "quoted": len(quotes), "error": error,
                  "quotes": quotes, "actual_fill": "UNKNOWN"}
        c.execute("INSERT INTO runs VALUES(?,?,?)", (day, key, dump(result)))
    return {k: v for k, v in result.items() if k != "quotes"}


def comparison(cache):
    result = {"enabled": enabled(), "status": "not_collected", "actual_fill": "UNKNOWN",
              "scope": "CONDITIONAL_CAPACITY_PAPER_ONLY", "variants": {}}
    path = Path(store_path(cache)).resolve()
    if not path.exists():
        return result
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as c:
            records = rows(c)
            runs = c.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        result.update(status="observed", observations=runs)
        for variant in (*SMART, *OVERNIGHT):
            selected = [r for r in records if r["variant"] == variant]
            closed = [r for r in selected if r["status"] == "CLOSED"]
            unresolved = [r for r in selected if r["status"] in ("PENDING", "OPEN", "UNRESOLVED")]
            net = sum(r["net"] for r in closed)
            result["variants"][variant] = {"intents": len(selected), "closed": len(closed),
                "unresolved": len(unresolved), "closed_modeled_net_subtotal": net,
                "complete_modeled_net": None if unresolved or not selected else net,
                "net_ex_best_winner": net - max([0.] + [r["net"] for r in closed]),
                "reserved_cash": sum(r["reserve"] for r in unresolved), "recent": selected[-20:]}
        pairs = {}
        for row in records:
            if row["variant"] in SMART:
                pairs.setdefault((row["day"], row["ticker"]), {})[row["variant"]] = row
        resolved = [p for p in pairs.values() if all(v in p and p[v]["status"] == "CLOSED" for v in SMART)]
        result["paired_smart"] = {
            "resolved_pairs": len(resolved), "unresolved_pairs": len(pairs) - len(resolved),
            "closed_pairs_morning_minus_close": sum(p[SMART[1]]["net"] - p[SMART[0]]["net"] for p in resolved),
            "scope": "SAME_FUNDED_ENTRY_CONDITIONAL_EXIT_COMPARISON",
        }
        return result
    except (sqlite3.Error, ValueError, KeyError, TypeError):
        return result | {"status": "unavailable"}
