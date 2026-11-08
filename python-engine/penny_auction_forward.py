"""Funded, clock-bound Penny auction paper comparisons. Never places orders.

All auction entries and exits are capacity assumptions, actual_fill UNKNOWN.
Open exposure (PENDING or OPEN) keeps cash reserved and makes complete modeled P&L unavailable.
A decision whose only evidence phase passed without usable evidence becomes NO_EVIDENCE: it stays
in the denominator, carries no modeled P&L and frees its cash and slot, because no later phase can
resolve it (Nov 8 Production clock review: as UNRESOLVED it held both books shut for good).
Legacy Smart/overnight stores are neither read as fills nor mutated.
"""
from __future__ import annotations

from contextlib import contextmanager, closing
from datetime import date, datetime, time
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
OPEN_EXPOSURE = ("PENDING", "OPEN")
NO_EVIDENCE = "NO_EVIDENCE"
LIVE_PACKET_AGE_SEC = 30
# A packet in a segment that sends nothing new before the receipt (the 09:12-09:15 auction
# buffer, the sparse 15:40-16:00 post-close book, after 16:00) is not stale for being old; it must
# be today's and from at least this time. Production Nov 5-6: at 16:03 every packet was 182-612 s old.
AUCTION_SETTLED_SINCE = time(9, 0)
CLOSE_SETTLED_SINCE = time(15, 30)
# The end of a PENDING row's only evidence phase; after it the row can never resolve.
EVIDENCE_ENDS = {"SMART": WINDOWS["MATCH"][1], "OVERNIGHT": WINDOWS["POST_END"][1]}
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


def quality(q, at, *, trade_window=None, settled_since=None):
    """Why the packet is not evidence at receipt ``at``, else None.

    A live session's packet must be at most 30 s old. With ``settled_since`` the segment sends
    nothing new until the receipt, so age is no fault; the packet must be today's, from
    ``settled_since`` on, and not after the receipt."""
    provider = stamp(q.get("timestamp"))
    if not provider or provider.date() != at.date():
        return "missing_or_cross_date_provider"
    age = (at - provider).total_seconds()
    if settled_since is None and not 0 <= age <= LIVE_PACKET_AGE_SEC:
        return "stale_or_future_provider"
    if settled_since is not None and (age < 0 or provider.time() < settled_since):
        return "future_or_unsettled_provider"
    if trade_window:
        trade = stamp(q.get("last_trade_time"))
        if (not trade or trade.date() != at.date() or trade > provider
                or not trade_window[0] <= trade.time() < trade_window[1]):
            return "no_supported_session_trade"
    return None


def traded_today(q, at):
    """The packet's last trade is today's and not after the packet: its price is today's."""
    trade, provider = stamp(q.get("last_trade_time")), stamp(q.get("timestamp"))
    return bool(trade and provider and trade.date() == at.date() and trade <= provider)


def later_volume(q, at, base):
    """(shares traded after ``base`` at its price, None) or (None, why the packet is no evidence).

    The post-close session trades only at the official close. A settled packet whose last trade
    is at or before the decision shows zero later volume: evidence of no capacity, not missing."""
    why = quality(q, at, settled_since=CLOSE_SETTLED_SINCE)
    if why:
        return None, why
    trade = stamp(q.get("last_trade_time"))
    if not traded_today(q, at) or trade.time() >= time(16):
        return None, "no_supported_session_trade"
    if not positive(q.get("volume")) or float(q["volume"]) < base["volume"]:
        return None, "volume_missing_or_reset"
    if trade <= stamp(base["at"]):
        return 0., None
    if not positive(q.get("last_price")) or abs(float(q["last_price"]) - base["price"]) >= .0001:
        return None, "postclose_price_changed"
    return float(q["volume"]) - base["volume"], None


def expire(c, at):
    """PENDING rows whose evidence phase has ended (the job missed it) become NO_EVIDENCE."""
    for r in rows(c):
        if r["status"] == "UNRESOLVED":          # written by the first version of this book
            r.update(status=NO_EVIDENCE)
        elif r["status"] == "PENDING":
            end = EVIDENCE_ENDS["SMART" if r["variant"] in SMART else "OVERNIGHT"]
            if at < datetime.combine(date.fromisoformat(r["day"]), end, IST):
                continue
            r.update(status=NO_EVIDENCE, reason="evidence_phase_not_observed")
        else:
            continue
        save(c, r)


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
    reserved = sum(r["reserve"] for r in held if r["status"] in OPEN_EXPOSURE)
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
    # Whether the 09:07 quote shows the auction at all: Production Nov 5-6, last_price equalled the
    # previous close on 125 of 125 pre-open quotes, so no gap (and no pick) was visible.
    moved = sum(1 for q in quotes.values() if positive(q.get("last_price"))
                and positive((q.get("ohlc") or {}).get("close"))
                and abs(float(q["last_price"]) - float(q["ohlc"]["close"])) > 1e-9)
    with store(cache) as c:
        if c.execute("SELECT 1 FROM sources WHERE family='SMART' AND day=?", (day,)).fetchone():
            return
        expire(c, at)
        cash = min(free_cash(c, v) for v in SMART)
        if any(r["variant"] in SMART and r["status"] in OPEN_EXPOSURE for r in rows(c)):
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
            "preopen_price_moved": moved, "picks": made, "refusals": refused, "paired_available_cash": cash,
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
    expire(c, at)
    if phase == "POST_BASE":
        source = (c.execute("SELECT payload FROM sources WHERE family='OVERNIGHT' AND day=?", (day,)).fetchone()
                  if settings.EDGE_OVERNIGHT_PAPER_ENABLED else None)
        if source:
            source = json.loads(source[0])
            for variant in OVERNIGHT:
                if variant == "OVERNIGHT_V3" and not source["v3_inputs_complete"]:
                    continue
                existing = [r for r in rows(c) if r["variant"] == variant
                            and (r["day"] == day or r["status"] in OPEN_EXPOSURE)]
                slots = 2 - len(existing)
                cash = free_cash(c, variant)
                ticket = cash / slots if slots > 0 else 0.
                for ticker in source[variant]:
                    if slots < 1 or any(r["ticker"] == ticker for r in existing):
                        continue
                    q = quotes.get(ticker) or {}
                    # The official close is the post-close session's only price and is in the quote
                    # from ~15:31 (Production Nov 5: 6 of 6 equal the daily close), so no 15:50 trade
                    # is needed to know it.
                    if (not postclose_base_ok(q, at)
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
            # Any trade today before 09:15 is the call auction's; nothing trades in the buffer.
            why = quality(q, at, trade_window=(AUCTION_SETTLED_SINCE, time(9, 15)),
                          settled_since=AUCTION_SETTLED_SINCE)
            opening = (q.get("ohlc") or {}).get("open")
            usable = not why and positive(opening) and positive(q.get("volume"))
            if r["variant"] in SMART and r["day"] == day and r["status"] == "PENDING":
                if not usable:
                    r.update(status=NO_EVIDENCE, reason=why or "missing_auction_price_or_volume")
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
            if postclose_base_ok(q, at) and positive(q.get("last_price")) and positive(q.get("volume")):
                r["close_intent"] = {"at": at.isoformat(), "price": float(q["last_price"]), "volume": float(q["volume"])}
        elif phase == "POST_END" and r["day"] == day:
            base = r.get("close_intent") if r["variant"] in SMART else {
                "at": r["intent_at"], "price": r["limit"], "volume": r.get("base_volume")}
            if not base or r["status"] not in OPEN_EXPOSURE:
                continue
            volume, why = later_volume(q, at, base)
            if r["variant"] in OVERNIGHT and r["status"] == "PENDING":
                if volume is None:
                    r.update(status=NO_EVIDENCE, reason=why)
                elif volume == 0:
                    r.update(status="REFUSED", reason="no_later_postclose_volume", later_volume=0.)
                else:
                    r["later_volume"] = volume
                    _modeled_entry(r, r["limit"], volume, .01)
            elif r["variant"] == SMART[0] and volume and volume * .01 >= r["modeled_quantity"]:
                close_row(r, base["price"], at, "POSTCLOSE_CAPACITY_MODEL")
        save(c, r)


def postclose_base_ok(q, at):
    """A decision packet after the close: settled since 15:30 and traded today (its price is today's close)."""
    return quality(q, at, settled_since=CLOSE_SETTLED_SINCE) is None and traded_today(q, at)


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
            names = {r["ticker"] for r in records if r["status"] in OPEN_EXPOSURE}
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
            smart_days = [s for s in (json.loads(p[0]) for p in c.execute(
                "SELECT payload FROM sources WHERE family='SMART'")) if "preopen_price_moved" in s]
        result.update(status="observed", observations=runs)
        for variant in (*SMART, *OVERNIGHT):
            selected = [r for r in records if r["variant"] == variant]
            closed = [r for r in selected if r["status"] == "CLOSED"]
            exposed = [r for r in selected if r["status"] in OPEN_EXPOSURE]
            net = sum(r["net"] for r in closed)
            result["variants"][variant] = {"intents": len(selected), "closed": len(closed),
                "unresolved": len(exposed),
                "no_evidence": sum(r["status"] in (NO_EVIDENCE, "UNRESOLVED") for r in selected),
                "refused": sum(r["status"] == "REFUSED" for r in selected),
                "closed_modeled_net_subtotal": net,
                "complete_modeled_net": None if exposed or not closed else net,
                "net_ex_best_winner": net - max([0.] + [r["net"] for r in closed]),
                "reserved_cash": sum(r["reserve"] for r in exposed), "recent": selected[-20:]}
        pairs = {}
        for row in records:
            if row["variant"] in SMART:
                pairs.setdefault((row["day"], row["ticker"]), {})[row["variant"]] = row
        resolved = [p for p in pairs.values() if all(v in p and p[v]["status"] == "CLOSED" for v in SMART)]
        result["paired_smart"] = {
            "resolved_pairs": len(resolved), "unresolved_pairs": len(pairs) - len(resolved),
            "no_evidence_pairs": sum(any(r["status"] in (NO_EVIDENCE, "UNRESOLVED") for r in p.values())
                                     for p in pairs.values()),
            "closed_pairs_morning_minus_close": sum(p[SMART[1]]["net"] - p[SMART[0]]["net"] for p in resolved),
            "scope": "SAME_FUNDED_ENTRY_CONDITIONAL_EXIT_COMPARISON",
        }
        seen = sum(int(s.get("requested") or 0) for s in smart_days)
        moved = sum(int(s.get("preopen_price_moved") or 0) for s in smart_days)
        result["smart_preopen_price"] = {
            "days": len(smart_days), "quotes": seen, "moved_from_previous_close": moved,
            # False: the 09:07 quote never showed the auction, so the Smart arms cannot pick.
            "visible": None if not seen else moved > 0}
        return result
    except (sqlite3.Error, ValueError, KeyError, TypeError):
        return result | {"status": "unavailable"}
