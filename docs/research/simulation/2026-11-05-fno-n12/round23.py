"""Two funded opening gap hypotheses that settle before native admissions."""
from bisect import bisect_left
from contextlib import closing
import copy
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import subprocess

from anatomy import trades
import round1 as r
from round16 import StraddleReplay
from config import settings
from fno_adaptive_risk import Close
from fno_chain import ChainSnapshot, _parity_forward, years_to_expiry
from fno_costs import calc_fno_costs
from fno_engine_mom import FnoDirection, MomSignal
from fno_entry_plan import EntryState, plan_single_leg_entry
from fno_n11 import backstop_points, stop_price

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "_local/india-vix/india-vol-closes.json"
REPAIR, HOLD = "EARLY_GAP_REPAIR", "EARLY_GAP_HOLD"
Y = r.Y
LOT = 65


@dataclass(frozen=True)
class Gap:
    side: int
    risk: float
    anchor: float
    repair_target: float | None


@dataclass
class Held:
    quote: object
    at: datetime
    side: int
    entry_underlying: float
    stop_underlying: float
    target_underlying: float
    premium_stop: float
    stress: float
    reason: str | None = None
    triggered_at: datetime | None = None


@lru_cache(maxsize=1)
def official():
    closes = json.loads(SOURCE.read_bytes())["closes"]
    return {day: row["nifty"] for day, row in closes.items() if row["nifty"] is not None}


def prior(closes, day):
    dates = sorted(closes)
    i = bisect_left(dates, day)
    if i < 21:
        return None
    prices = [closes[d] for d in dates[i - 21:i]]
    deviation = math.sqrt(sum(math.log(b / a) ** 2 for a, b in zip(prices, prices[1:])) / 20.)
    return prices[-1], prices[-1] * deviation


def setup(mode, opened, first_close, last_close, previous, daily_points, future, future_range):
    gap = opened - previous
    if daily_points <= 0. or abs(gap) < .45 * daily_points or future_range <= 0.:
        return None
    sign = 1 if gap > 0. else -1
    remaining = (last_close - previous) / gap
    drift = sign * (last_close - first_close)
    risk = min(45., max(12., .35 * future_range))
    if mode == REPAIR and .15 <= remaining <= .65 and drift < 0.:
        return Gap(-sign, risk, future, future + previous - last_close)
    if mode == HOLD and remaining >= .85 and drift > 0.:
        return Gap(sign, risk, future, None)
    return None


def fill_levels(signal, future):
    if abs(future - signal.anchor) > .25 * signal.risk:
        return None
    stop = future - signal.side * signal.risk
    target = signal.repair_target if signal.repair_target is not None else future + signal.side * 1.8 * signal.risk
    return (stop, target) if signal.side * (target - future) >= 1.5 * signal.risk else None


def reason_at(held, future, bid, minute):
    if held.side * (future - held.stop_underlying) <= 0.:
        return "underlying_stop"
    if bid is not None and bid <= held.premium_stop:
        return "premium_backstop"
    if held.side * (future - held.target_underlying) >= 0.:
        return "early_target"
    return "early_clock" if minute >= 580 else None


class EarlyReplay(Y.BookReplay):
    mark = StraddleReplay.mark
    early_held = None
    incomplete = False

    def minutes(self, day, kind, expiry):
        rows = self.raw.execute(
            "SELECT substr(datetime,12),open,high,low,close FROM candles WHERE kind=? AND expiry=? AND strike=0 AND opt='' "
            "AND datetime BETWEEN ? AND ? ORDER BY datetime", (kind, expiry, day + " 09:15:00", day + " 09:24:00"),
        ).fetchall()
        if [at for at, *_ in rows] != [f"09:{m:02d}:00" for m in range(15, 25)]:
            return None
        if any(not (0. < low <= min(opened, close) <= max(opened, close) <= high)
               for _, opened, high, low, close in rows):
            return None
        return rows

    def _entry(self, book, obs, frame, day, now):
        if self.incomplete:
            return
        if now.hour * 60 + now.minute >= 585 and getattr(self, "early_day", None) != day:
            self.early_day = day
            self.replay_opening(book, frame, day, now)
        if not self.incomplete:
            super()._entry(book, obs, frame, day, now)

    def replay_opening(self, book, frame, day, native_time):
        expiry = next((d for d in self.data.option_expiries()[0] if d >= native_time.date()), None)
        if expiry is None or expiry == native_time.date() or book.open or book.entries_today[native_time.date()]:
            return
        index = self.minutes(day, "index", "")
        previous = prior(official(), day)
        if index is None or previous is None:
            self.notes["early_missing_opening_input"] += 1
            return
        gap_size = abs(index[0][1] - previous[0])
        if gap_size < .45 * previous[1]:
            return
        observations, _ = self.data.observations(day)
        marks = {o.at.strftime("%H:%M:%S"): o for o in observations if o.at < native_time}
        decision, execution = marks.get("09:25:59"), marks.get("09:26:59")
        if decision is None or execution is None:
            self.notes["early_missing_decision_or_execution_clock"] += 1
            return
        futures = self.minutes(day, "future", decision.future.contract.expiry.isoformat())
        if futures is None:
            self.notes["early_missing_opening_input"] += 1
            return
        width = max(row[2] for row in futures) - min(row[3] for row in futures)
        signal = setup(self.book["n12_early"], index[0][1], index[4][4], index[-1][4], *previous, decision.future.ltp, width)
        if not signal:
            return
        self.notes["early_signal"] += 1
        self.open_early(book, execution, frame, day, execution.at, expiry, signal)
        for clock in sorted(marks):
            if self.early_held and "09:26:59" < clock < "09:45:00":
                self.manage_early(book, marks[clock], marks[clock].at)
        if self.early_held:
            self.incomplete = True
            self.notes["early_unresolved_before_native"] += 1
            held = self.early_held
            book.trades.append({"tradingsymbol": held.quote.contract.tradingsymbol, "entry_time": held.at.isoformat(),
                                "status": "UNRESOLVED", "n12_early": self.book["n12_early"]})
            self.early_held = None

    def open_early(self, book, obs, frame, day, now, expiry, gap):
        if book.open or book.entries_today[now.date()] or self._halts(book, now):
            self.notes["early_shared_brake"] += 1
            return
        stance = self._stance(book, now)
        if stance.single_leg_halted_today or r.f.L.R.stand_aside(r.f.L.vol_at(now, .9), r.f.L.paper_before(now), 20):
            self.notes["early_shared_brake"] += 1
            return
        bar = Y.replay._last_closed_bar(frame, now)
        if bar is None:
            return
        regime, _ = self.data.regime(bar, day)
        future = obs.future.ltp
        levels = fill_levels(gap, future)
        if levels is None:
            self.notes["early_stale_or_reward"] += 1
            return
        stop, target = levels
        quotes = {(q.contract.strike, q.contract.instrument_type): q for q in obs.options.values()
                  if q.contract.expiry == expiry and q.contract.lot_size == LOT}
        if not quotes:
            self.notes["early_missing_chain"] += 1
            return
        atm = min((strike for strike, _ in quotes), key=lambda strike: (abs(strike - future), strike))
        snap = ChainSnapshot(obs.at, expiry, future, _parity_forward(quotes, atm, years_to_expiry(expiry, obs.at)),
                             LOT, obs.future, quotes)
        signal = MomSignal(bar_ts=bar, direction=FnoDirection.LONG if gap.side == 1 else FnoDirection.SHORT,
                           close=future, atr=gap.risk, stop_underlying=stop, target_underlying=target,
                           strategy=self.book["n12_early"])
        state = EntryState(book.equity, 0., 0, 0, (), frozenset(), True, False, stance.multiplier, lot_ceiling=1)
        saved = settings.FNO_ENTRY_START_MIN
        assert saved >= 585
        try:
            settings.FNO_ENTRY_START_MIN = 566
            plan = plan_single_leg_entry(signal, snap, regime, now, state)
        finally:
            settings.FNO_ENTRY_START_MIN = saved
        if not plan.accepted:
            self.notes[f"early_plan_refused:{plan.reject_reason}"] += 1
            return
        quote = plan.quote
        ask = self.mark(obs, quote.contract.token, now, buying=True)
        stress = r.f.T.R.extra_cost(self.book.get("cost"), 1)
        if ask is None or plan.lots != 1:
            self.notes["early_missing_fill"] += 1
            return
        if LOT * ask + calc_fno_costs(ask, ask, LOT) + stress > min(9000., book.equity):
            self.notes["early_cash_refused"] += 1
            return
        loss_points = backstop_points(1600., ask, LOT, stress, calc_fno_costs)
        premium_stop = max(.75 * ask, stop_price(ask, loss_points)) if loss_points is not None else ask
        if premium_stop >= quote.bid:
            self.notes["early_backstop_refused"] += 1
            return
        self.early_held = Held(quote, now, gap.side, future, stop, target, premium_stop, stress)
        book.entries_today[now.date()] += 1
        self.notes["early_admitted"] += 1

    def manage_early(self, book, obs, now):
        held = self.early_held
        assert held and now.date() == held.at.date()
        minute = now.hour * 60 + now.minute
        assert minute < 585
        bid = self.mark(obs, held.quote.contract.token, now)
        if held.reason is None:
            held.reason = reason_at(held, obs.future.ltp, bid, minute)
            if held.reason:
                held.triggered_at = now
            return
        if bid is None or now <= held.triggered_at:
            return
        ask = held.quote.ask
        gross = (bid - ask) * LOT
        fees = calc_fno_costs(ask, bid, LOT)
        net = gross - fees - held.stress
        book.equity += net
        book.closes.append((now, net, "SINGLE_LEG"))
        book.completed.append(Close(now, net, True))
        book.trades.append({
            "tradingsymbol": held.quote.contract.tradingsymbol, "entry_time": held.at.isoformat(),
            "entry_premium": ask, "entry_qty": LOT, "entry_underlying": held.entry_underlying,
            "stop_underlying": held.stop_underlying, "target_underlying": held.target_underlying,
            "direction": "LONG" if held.side == 1 else "SHORT", "premium_stop": held.premium_stop,
            "exit_time": now.isoformat(), "exit_premium": bid, "exit_reason": held.reason,
            "triggered_at": held.triggered_at.isoformat(), "gross_pnl": gross, "fees": fees,
            "extra_cost": held.stress, "net_pnl": net, "status": "CLOSED", "n12_early": self.book["n12_early"],
        })
        self.early_held = None
        self.notes["early_settled_before_native"] += 1

    def run(self, start, end):
        assert not self.data.paper_closes(), "opening prefix needs a source without exogenous settlements"
        with closing(self.data._connect()) as self.raw:
            return super().run(start, end)


def books():
    return {name: {**copy.deepcopy(r.books()["N11T"]), "label": f"N12|{name}", "n12_early": name}
            for name in (REPAIR, HOLD)}


def main():
    spec = HERE / "round23-freeze.json"
    cfg = json.loads(spec.read_bytes())
    assert cfg == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{spec.relative_to(r.ROOT).as_posix()}"], cwd=r.ROOT))
    for name, sha in cfg["source"].items():
        assert hashlib.sha256((HERE / name).read_text(encoding="utf-8").encode()).hexdigest() == sha
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == cfg["official"]
    assert cfg["books"] == json.loads(json.dumps(books()))
    r.verify_freeze()
    dataset = r.DATASETS[r.YEAR]
    manifest = json.loads((dataset / "manifest.json").read_bytes())
    with (dataset / "breeze.sqlite").open("rb") as handle:
        assert hashlib.file_digest(handle, "sha256").hexdigest() == manifest["files_sha256"]["breeze.sqlite"]
    controls = {name: r.raw_for(r.books()[name]) for name in ("N11", "N11T")}
    for name, raw in controls.items():
        assert r.money(raw) == r.money(trades(r.YEAR, name)[1]), name
    r.f.Z.N.B.O27F.deny_network()
    r.f.Z.N.B.L._init()
    results = {}
    for name, model in books().items():
        with Y.ROUTER.dispatch():
            engine = EarlyReplay(Y.dataset("year"), model, Y.table("year"), "year")
            results[name] = engine.run(*r.WINDOW)
        for row in results[name]["trades"]:
            row.setdefault("status", "CLOSED" if row.get("net_pnl") is not None else "UNRESOLVED")
    out = {name: r.metrics(raw) for name, raw in {**controls, **results}.items()}
    out["early_trades"] = {name: [t for t in raw["trades"] if t.get("n12_early")] for name, raw in results.items()}
    with (HERE / f"round23-{r.YEAR}.json").open("x", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    for name in results:
        row = out[name]
        print(r.YEAR, name, row["net"], row["unresolved"],
              {k: v for k, v in row["notes"].items() if k.startswith("early_")}, flush=True)


if __name__ == "__main__":
    main()
