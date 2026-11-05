"""Shared N11T paper replay with an independently timed, staged range spread."""
from collections import Counter
import copy
from dataclasses import dataclass, field
from datetime import date
import json
import math
from pathlib import Path
import subprocess

import pandas as pd

import round1 as r
from config import settings
from fno_adaptive_risk import Close
from fno_costs import calc_fno_costs
from fno_defined_risk import _profile
from fno_models import Leg, OptionType

HERE = Path(__file__).resolve().parent
Y = r.Y
LOT = 65
WING = 100
STEP = 50


@dataclass
class Ticket:
    day: str
    expiry: date
    short_put: float
    short_call: float
    contracts: tuple
    state: str = "BUY_WINGS"
    buys: dict = field(default_factory=dict)
    sells: dict = field(default_factory=dict)
    opened_at: object = None
    credit: float = 0.
    reason: str = ""


def box(frame, now):
    start = pd.Timestamp(now.replace(tzinfo=None)).normalize() + pd.Timedelta(hours=9, minutes=15)
    opening = frame.loc[start:start + pd.Timedelta(minutes=70)]
    if len(opening) != 15 or opening.index[-1] + pd.Timedelta(minutes=5) > pd.Timestamp(now.replace(tzinfo=None)):
        return None
    if not all(b - a == pd.Timedelta(minutes=5) for a, b in zip(opening.index, opening.index[1:])):
        return None
    high, low = float(opening.high.max()), float(opening.low.min())
    width = high - low
    last = float(opening.close.iloc[-1])
    first, final = opening.iloc[:9], opening.iloc[9:]
    if width <= 0 or abs(last - float(opening.open.iloc[0])) > .25 * width:
        return None
    if not low + .25 * width <= last <= high - .25 * width:
        return None
    if float(final.high.max() - final.low.min()) > .50 * float(first.high.max() - first.low.min()):
        return None
    return low, high


def candidates(obs, expiry, now):
    atm = round(obs.future.ltp / STEP) * STEP
    return {(q.contract.strike, q.contract.instrument_type): q for q in obs.options.values()
            if q.contract.expiry == expiry and q.contract.lot_size == LOT
            and abs(q.contract.strike - atm) <= 5 * STEP and usable(q, now)}


def usable(quote, now):
    return (quote.last_trade_time == now and quote.oi >= settings.FNO_MIN_OI
            and quote.volume >= settings.FNO_MIN_VOL and quote.ask >= quote.bid > 0
            and quote.ask_quantity >= LOT and quote.bid_quantity >= LOT
            and quote.spread_pct <= settings.FNO_MAX_SPREAD_PCT)


def prices(quotes, tokens, side, now):
    chosen = {}
    for token in tokens:
        q = quotes.get(token)
        if q is None or not usable(q, now):
            return None
        chosen[token] = float(getattr(q, side))
    return chosen


def fit(contracts, buys, sells):
    legs = [Leg(opt_type=OptionType(c.instrument_type), strike=c.strike,
                quantity=1 if c.token in buys else -1,
                premium=buys.get(c.token, sells.get(c.token))) for c in contracts]
    unit_credit, _, loss, _ = _profile(legs, LOT)
    fees = sum(calc_fno_costs(leg.premium, leg.premium, LOT) for leg in legs)
    return unit_credit * LOT, loss + fees + 400.


class RangeReplay(Y.BookReplay):
    ticket = None
    attempted = None
    incomplete = False

    def _entry(self, book, obs, frame, day, now):
        if self.ticket is not None or self.incomplete:
            return
        super()._entry(book, obs, frame, day, now)
        if self.attempted == day or not 630 <= now.hour * 60 + now.minute <= 633:
            return
        self.attempted = day
        if book.open or book.entries_today[now.date()] or self._halts(book, now):
            return
        if self._stance(book, now).single_leg_halted_today:
            return
        bar = Y.replay._last_closed_bar(frame, now)
        regime, _ = self.data.regime(bar, day)
        if regime == "REGIME_3_CRISIS":
            return
        expiry = next((e for e in self.data.option_expiries()[0] if e >= now.date()), None)
        if expiry is None or not 1 <= (expiry - now.date()).days <= 2:
            return
        bounds = box(frame, now)
        if bounds is None:
            return
        self.notes["range_box"] += 1
        low, high = bounds
        short_put = math.floor(low / STEP) * STEP - STEP
        short_call = math.ceil(high / STEP) * STEP + STEP
        keys = ((short_put - WING, "PE"), (short_call + WING, "CE"),
                (short_put, "PE"), (short_call, "CE"))
        available = candidates(obs, expiry, now)
        if not all(key in available for key in keys):
            self.notes["range_missing_chain"] += 1
            return
        wings, shorts = [available[key] for key in keys[:2]], [available[key] for key in keys[2:]]
        contracts = tuple(q.contract for q in (*wings, *shorts))
        credit, risk = fit(contracts, {q.contract.token: q.ask for q in wings},
                           {q.contract.token: q.bid for q in shorts})
        reserve = LOT * (WING + sum(q.ask for q in wings)) + 1200.
        if credit < 1100. or risk > 5000. or reserve > .15 * book.equity:
            self.notes["range_funding_or_terms"] += 1
            return
        self.ticket = Ticket(day, expiry, short_put, short_call, contracts)

    def _settle(self, book, now, wing_exit):
        t = self.ticket
        costs = sum(calc_fno_costs(a, wing_exit[k], LOT) for k, a in t.buys.items())
        gross = sum((wing_exit[k] - a) * LOT for k, a in t.buys.items())
        for token, opening in t.sells.items():
            close = t.cover[token]
            costs += calc_fno_costs(close, opening, LOT)
            gross += (opening - close) * LOT
        stress = 400. if t.sells else 200.
        net = gross - costs - stress
        book.equity += net
        book.closes.append((now, net, "DEFINED_RISK"))
        book.completed.append(Close(now, net, False))
        book.trades.append({
            "tradingsymbol": "NIFTY_RANGE_CONDOR", "entry_time": t.opened_at.isoformat(),
            "exit_time": now.isoformat(), "exit_reason": t.reason, "status": "CLOSED",
            "gross_pnl": gross, "fees": costs, "extra_cost": stress, "net_pnl": net,
            "wing_buys": t.buys, "wing_exits": wing_exit, "short_sales": t.sells,
            "short_covers": t.cover if t.sells else {}, "expiry": t.expiry.isoformat(),
        })
        self.notes["range_settled"] += 1
        self.ticket = None

    def _manage(self, book, obs, now):
        super()._manage(book, obs, now)
        t = self.ticket
        if t is None:
            return
        if t.day != now.date().isoformat():
            self.incomplete = True
            self.ticket = None
            self.notes["range_unresolved"] += 1
            return
        wings = tuple(c.token for c in t.contracts[:2])
        shorts = tuple(c.token for c in t.contracts[2:])
        minute = now.hour * 60 + now.minute
        quotes = obs.options
        if t.state == "BUY_WINGS":
            asks = prices(quotes, wings, "ask", now)
            shorts_now = prices(quotes, shorts, "bid", now)
            if not asks or not shorts_now:
                self.ticket = None
                return
            credit, risk = fit(t.contracts, asks, shorts_now)
            if credit < 1100. or risk > 5000. or LOT * (WING + sum(asks.values())) + 1200. > .15 * book.equity:
                self.ticket = None
                return
            t.buys, t.opened_at, t.state = asks, now, "SELL_SHORTS"
            book.entries_today[now.date()] += 1
        elif t.state == "SELL_SHORTS":
            bids = prices(quotes, shorts, "bid", now)
            credit, risk = fit(t.contracts, t.buys, bids) if bids else (0., math.inf)
            if credit < 1100. or risk > 5000.:
                t.state, t.reason = "SELL_WINGS", "range_abandoned"
            else:
                t.sells, t.credit, t.state = bids, credit, "HOLD"
                self.notes["range_full_spread"] += 1
        elif t.state == "HOLD":
            cover = prices(quotes, shorts, "ask", now)
            bid = prices(quotes, wings, "bid", now)
            debit = LOT * (sum(cover.values()) - sum(bid.values())) if cover and bid else None
            if minute >= settings.FNO_HARD_FLAT_MIN:
                t.reason = "range_hard_flat"
            elif not t.short_put < obs.future.ltp < t.short_call or (debit is not None and debit >= 2. * t.credit):
                t.reason = "range_stop"
            elif debit is not None and debit <= .60 * t.credit:
                t.reason = "range_target"
            if t.reason:
                t.state = "COVER_SHORTS"
        elif t.state == "COVER_SHORTS":
            cover = prices(quotes, shorts, "ask", now)
            if cover:
                t.cover, t.state = cover, "SELL_WINGS"
        else:
            wing_exit = prices(quotes, wings, "bid", now)
            if wing_exit:
                self._settle(book, now, wing_exit)

    def run(self, start, end):
        out = super().run(start, end)
        if self.incomplete or self.ticket is not None:
            out["trades"].append({"tradingsymbol": "NIFTY_RANGE_CONDOR", "status": "UNRESOLVED"})
        return out


def main():
    freeze = HERE / "round12-freeze.json"
    spec = json.loads(freeze.read_bytes())
    assert spec == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{freeze.relative_to(r.ROOT).as_posix()}"], cwd=r.ROOT))
    from hashlib import sha256
    for file, sha in spec["files"].items():
        assert sha256((HERE / file).read_bytes()).hexdigest() == sha
    r.verify_freeze()
    r.f.Z.N.B.L._init()
    book = copy.deepcopy(r.books()["N11T"])
    book["label"] = "N12|FUNDED_RANGE"
    with Y.ROUTER.dispatch():
        engine = RangeReplay(Y.dataset("year"), book, Y.table("year"), "year")
        data = engine.run(*r.WINDOW)
    for row in data["trades"]:
        row.setdefault("status", "CLOSED" if row.get("net_pnl") is not None else "UNRESOLVED")
    controls = {name: r.raw_for(r.books()[name]) for name in ("N11", "N11T")}
    for name, raw in controls.items():
        from anatomy import trades
        assert r.money(raw) == r.money(trades(r.YEAR, name)[1]), name
    result = {name: r.metrics(raw) for name, raw in {**controls, "FUNDED_RANGE": data}.items()}
    result["range_positions"] = [x for x in data["trades"] if x["tradingsymbol"] == "NIFTY_RANGE_CONDOR"]
    with (HERE / f"round12-{r.YEAR}.json").open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2, sort_keys=True, default=str)
        file.write("\n")
    print(r.YEAR, "candidate", result["FUNDED_RANGE"]["net"], "control", result["N11T"]["net"],
          "range", result["FUNDED_RANGE"]["notes"], flush=True)


if __name__ == "__main__":
    main()
