"""Causal option-wing direction with a forecast-scaled one-lot risk template."""
from bisect import bisect_left
from contextlib import closing
import copy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import subprocess

import pandas as pd

from anatomy import trades
import round1 as r
from round16 import StraddleReplay
from config import settings
from fno_chain import RISK_FREE_RATE, years_to_expiry
from fno_engine_mom import FnoDirection, MomSignal
from options_math import implied_vol

HERE = Path(__file__).resolve().parent
Y = r.Y
T = r.f.T
ADD = T.maybe_add
NAME = "WING_SKEW"


@lru_cache(maxsize=1)
def forecasts():
    return json.loads((HERE / "round18-forecasts.json").read_bytes())


def neighbors(strikes, target, forward, right):
    candidates = sorted(k for k in strikes if (k < forward if right == "PE" else k > forward))
    i = bisect_left(candidates, target)
    if i < len(candidates) and candidates[i] == target:
        return (candidates[i],)
    if 0 < i < len(candidates) and candidates[i] - candidates[i - 1] == 50.:
        return (candidates[i - 1], candidates[i])
    return ()


def wing_iv(quotes, target, forward, time, right, mark):
    strikes = neighbors(quotes, target, forward, right)
    values = []
    for k in strikes:
        q = quotes[k]
        if mark(q.contract.token) is None:
            return None
        value = implied_vol(q.mid, forward, k, time, RISK_FREE_RATE, right == "CE")
        if value is None:
            return None
        values.append(value)
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return values[0] + (values[1] - values[0]) * (target - strikes[0]) / (strikes[1] - strikes[0])
    return None


def market_skew(obs, expiry, now, mark):
    choices = {right: {q.contract.strike: q for q in obs.options.values()
                       if q.contract.expiry == expiry and q.contract.instrument_type == right}
               for right in ("CE", "PE")}
    atm = 50 * math.floor(obs.future.ltp / 50 + .5)
    call, put = (choices[right].get(atm) for right in ("CE", "PE"))
    if call is None or put is None or any(mark(q.contract.token) is None for q in (call, put)):
        return None
    tau = years_to_expiry(expiry, now)
    forward = atm + (call.mid - put.mid) * math.exp(RISK_FREE_RATE * tau)
    if not .995 * obs.future.ltp <= forward <= 1.005 * obs.future.ltp:
        return None
    left = wing_iv(choices["PE"], .996 * forward, forward, tau, "PE", mark)
    right = wing_iv(choices["CE"], 1.004 * forward, forward, tau, "CE", mark)
    return left - right if left is not None and right is not None else None


def trade_signal(frame, now, future, pending):
    side, opening, move = pending
    if not -.15 * move <= side * (future - opening) <= .40 * move:
        return None
    ts = Y.replay._last_closed_bar(frame, now)
    if ts is None:
        return None
    expected = pd.date_range(end=pd.Timestamp(ts), periods=7, freq="5min")
    if expected[0].date() != now.date() or not expected.isin(frame.index).all():
        return None
    recent = frame.loc[expected]
    highs, lows, closes = (recent[k].to_list() for k in ("high", "low", "close"))
    atr = sum(max(hi - lo, abs(hi - prev), abs(lo - prev))
              for hi, lo, prev in zip(highs[1:], lows[1:], closes)) / 6.
    if atr <= 0:
        return None
    risk = max(.70 * atr, min(1.25 * atr, .25 * move))
    return MomSignal(bar_ts=ts, direction=FnoDirection.LONG if side == 1 else FnoDirection.SHORT,
                     close=closes[-1], atr=atr, stop_underlying=future - side * risk,
                     target_underlying=future + side * 2. * risk, strategy=NAME)


class SkewReplay(Y.BookReplay):
    mark = StraddleReplay.mark

    def _capture(self, obs, now, day, minute):
        if minute == 585:
            self.skew_first = self.skew_pending = None
        estimate = forecasts().get(day)
        if estimate is None:
            return
        expiry = next((d for d in self.data.option_expiries()[0] if d >= now.date()), None)
        if expiry is None or not 1 <= (expiry - now.date()).days <= 6:
            return
        value = market_skew(obs, expiry, now, lambda token: self.mark(obs, token, now, buying=True))
        if value is None:
            self.notes[f"skew_missing_chain_{minute}"] += 1
            return
        if minute == 585:
            self.skew_first = day, expiry, value, obs.future.ltp
            return
        prior = getattr(self, "skew_first", None)
        if prior is None or prior[:2] != (day, expiry):
            return
        self.notes["skew_both_snapshots"] += 1
        change = value - prior[2]
        if abs(change) <= .01:
            return
        side = -1 if change > 0 else 1
        opening = prior[3]
        move = opening * math.sqrt(math.exp(estimate[1]) / 252.)
        if not -.15 * move <= side * (obs.future.ltp - opening) <= .40 * move:
            self.notes["skew_price_move_refused"] += 1
            return
        self.skew_pending = day, (side, opening, move)
        self.notes["skew_candidate_day"] += 1

    def _entry(self, book, obs, frame, day, now):
        minute = now.hour * 60 + now.minute
        if minute in (585, 615):
            self._capture(obs, now, day, minute)
        self.skew_context = book, obs.future.ltp
        before = book.next_id
        try:
            result = super()._entry(book, obs, frame, day, now)
            if book.next_id > before and self.leg_member[before] == 5:
                assert book.open[before].lots == 1
                self.notes["skew_admitted"] += 1
            return result
        finally:
            self.skew_context = None

    def route(self, frame, regime, now):
        native = super().route(frame, regime, now)
        if native.direction is not None or now.hour * 60 + now.minute != 616:
            return native
        pending = getattr(self, "skew_pending", None)
        if not pending or pending[0] != now.date().isoformat():
            return native
        self.skew_pending = None
        book, future = self.skew_context
        if book.open or regime == "REGIME_3_CRISIS":
            return native
        if r.f.L.R.stand_aside(r.f.L.vol_at(now, .9), r.f.L.paper_before(now), 20):
            return native
        signal = trade_signal(frame, now, future, pending[1])
        if signal is None:
            return native
        self._fired = 5
        self._n02_decision = {"selected_profile": "N12", "selector_policy": "STATIC", "selection_asof": None,
                              "signal_bar": signal.bar_ts, "selection_latest_label_exit": None,
                              "origin": NAME, "entry_expert": NAME, "entry_gate": "FLAT"}
        settings.FNO_MAX_LOTS = min(settings.FNO_MAX_LOTS, 1)
        settings.FNO_MAX_LOTS_PROVEN = min(settings.FNO_MAX_LOTS_PROVEN, 1)
        self.notes["skew_planner_attempt"] += 1
        return signal

    def run(self, start, end):
        with closing(self.data._connect()) as self.raw:
            return super().run(start, end)


def maybe_add(self, book, leg, obs, now):
    if self.book.get("n12_skew") != NAME or self.leg_member[leg.id] != 5:
        return ADD(self, book, leg, obs, now)


def book_for_run():
    book = copy.deepcopy(r.books()["N11T"])
    book.update(label="N12|WING_SKEW", n12_skew=NAME)
    book["members"].append(copy.deepcopy(book["members"][3]))
    return book


T.maybe_add = maybe_add


def main():
    spec = HERE / "round20-freeze.json"
    frozen = json.loads(spec.read_bytes())
    assert frozen == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{spec.relative_to(r.ROOT).as_posix()}"], cwd=r.ROOT))
    for name, sha in frozen["source"].items():
        assert hashlib.sha256((HERE / name).read_text(encoding="utf-8").encode()).hexdigest() == sha
    assert frozen["book"] == json.loads(json.dumps(book_for_run()))
    r.verify_freeze()
    dataset = r.DATASETS[r.YEAR]
    expected = json.loads((dataset / "manifest.json").read_bytes())["files_sha256"]["breeze.sqlite"]
    with (dataset / "breeze.sqlite").open("rb") as handle:
        assert hashlib.file_digest(handle, "sha256").hexdigest() == expected
    controls = {name: r.raw_for(r.books()[name]) for name in ("N11", "N11T")}
    for name, raw in controls.items():
        assert r.money(raw) == r.money(trades(r.YEAR, name)[1]), name
    r.f.Z.N.B.O27F.deny_network()
    r.f.Z.N.B.L._init()
    with Y.ROUTER.dispatch():
        engine = SkewReplay(Y.dataset("year"), book_for_run(), Y.table("year"), "year")
        data = engine.run(*r.WINDOW)
    for row in data["trades"]:
        row.setdefault("status", "CLOSED" if row.get("net_pnl") is not None else "UNRESOLVED")
    result = {name: r.metrics(raw) for name, raw in {**controls, NAME: data}.items()}
    result["candidate_trades"] = [t for t in data["trades"] if t.get("member") == 5]
    with (HERE / f"round20-{r.YEAR}.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    row = result[NAME]
    print(r.YEAR, row["net"], row["worst_day"], {k: n for k, n in row["notes"].items() if k.startswith("skew_")}, flush=True)


if __name__ == "__main__":
    main()
