"""One regular NIFTY continuation attempt after a booked native winner."""

from contextlib import contextmanager
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess

import pandas as pd

from anatomy import trades
import round1 as r
from config import settings
from fno_costs import calc_fno_costs
from fno_engine_mom import FnoDirection, MomSignal
from fno_n11 import backstop_points, stop_price


HERE = Path(__file__).resolve().parent
Y = r.Y
T = r.f.T
PLAN = T._planner
ADD = T.maybe_add
NAME = "BANKED_RETEST"
MEMBER = 5


def earned_budget(net):
    return min(2000., .5 * net) if net >= 1800. else None


def structure(side, risk, anchor, future, previous, current):
    retrace = side * (anchor - previous.close)
    width = current.high - current.low
    if not .15 * risk <= retrace <= .60 * risk or width <= 0:
        return None
    if side * (current.close - current.open) < .5 * width or side * (current.close - anchor) <= 0:
        return None
    if not 0 < side * (future - anchor) <= .35 * risk:
        return None
    edge = min(previous.low, current.low) if side == 1 else max(previous.high, current.high)
    stop = edge - side * .10 * risk
    distance = side * (future - stop)
    if .25 * risk <= distance <= 1.25 * risk:
        return stop, future + side * 2.25 * distance
    return None


def signal_after_winner(closed, frame, now, future):
    entry, stop, anchor = (closed.get(key) for key in ("entry_underlying", "initial_stop_underlying", "exit_underlying"))
    if any(value is None for value in (entry, stop, anchor)):
        return None
    side = 1 if closed["direction"] == "LONG" else -1
    risk = side * (entry - stop)
    if risk <= 0 or side * (anchor - entry) < .75 * risk:
        return None
    at = pd.Timestamp(now.replace(tzinfo=None))
    exit_at = pd.Timestamp(datetime.fromisoformat(closed["exit_time"]).replace(tzinfo=None))
    if not 0 < (at - exit_at).total_seconds() <= 1800:
        return None
    bar_ts = Y.replay._last_closed_bar(frame, now)
    if bar_ts is None:
        return None
    expected = pd.date_range(end=pd.Timestamp(bar_ts), periods=7, freq="5min")
    if expected[-2] <= exit_at or expected[0].date() != at.date() or not expected.isin(frame.index).all():
        return None
    recent = frame.loc[expected]
    previous, current = recent.iloc[-2], recent.iloc[-1]
    levels = structure(side, risk, anchor, future, previous, current)
    if levels is None:
        return None
    high, low, close = (recent[key].to_list() for key in ("high", "low", "close"))
    atr = sum(max(hi - lo, abs(hi - prior), abs(lo - prior)) for hi, lo, prior in zip(high[1:], low[1:], close)) / 6
    if atr <= 0:
        return None
    return MomSignal(bar_ts=bar_ts, direction=FnoDirection.LONG if side == 1 else FnoDirection.SHORT,
                     close=current.close, atr=atr, stop_underlying=levels[0], target_underlying=levels[1], strategy=NAME)


class RetestReplay(Y.BookReplay):
    def _entry(self, book, obs, frame, day, now):
        self.retest_context = book, obs.future.ltp
        self.retest_backstop = None
        before = book.next_id
        try:
            result = super()._entry(book, obs, frame, day, now)
            if book.next_id > before and self.leg_member[before] == MEMBER:
                leg = book.open[before]
                assert leg.lots == 1 and self.retest_backstop is not None
                leg.premium_stop = max(leg.premium_stop, self.retest_backstop)
                self.notes["retest_admitted"] += 1
            return result
        finally:
            self.retest_context = None

    def route(self, frame, regime, now):
        native = super().route(frame, regime, now)
        minute = now.hour * 60 + now.minute
        if native.direction is not None or not 615 <= minute <= 840 or getattr(self, "retest_day", None) == now.date():
            return native
        book, future = self.retest_context
        if book.open or not book.trades or regime == "REGIME_3_CRISIS":
            return native
        closed = book.trades[-1]
        if (closed.get("member") == MEMBER or not closed.get("exit_time", "").startswith(now.date().isoformat())
                or closed.get("net_pnl", 0.) <= 0):
            return native
        limit = earned_budget(r.f.L.realised_today(book, now))
        if limit is None:
            return native
        signal = signal_after_winner(closed, frame, now, future)
        if signal is None:
            return native
        self.retest_day = now.date()
        self.notes["retest_setup"] += 1
        if r.f.L.R.stand_aside(r.f.L.vol_at(now, .9), r.f.L.paper_before(now), 20):
            self.notes["retest_stand_aside"] += 1
            return native
        self.retest_limit = limit
        self._fired = MEMBER
        self._n02_decision = {"selected_profile": "N12", "selector_policy": "STATIC", "selection_asof": None,
                              "selection_latest_label_exit": None, "signal_bar": signal.bar_ts,
                              "origin": NAME, "entry_expert": NAME, "entry_gate": "BOOKED_GAIN"}
        settings.FNO_MAX_LOTS = min(settings.FNO_MAX_LOTS, 1)
        settings.FNO_MAX_LOTS_PROVEN = min(settings.FNO_MAX_LOTS_PROVEN, 1)
        return signal


def planner(sig, snap, regime, now, state):
    plan = PLAN(sig, snap, regime, now, state)
    if sig.strategy != NAME:
        return plan
    engine = T.ENGINE["now"]
    if not plan.accepted:
        engine.notes[f"retest_refusal:{plan.reject_reason}"] += 1
        return plan
    extra = T.R.extra_cost(engine.book["cost"], plan.lots)
    points = backstop_points(engine.retest_limit, plan.quote.ask, plan.lot_size, extra, calc_fno_costs)
    backstop = stop_price(plan.quote.ask, points) if points is not None else None
    if backstop is None or backstop >= plan.quote.bid:
        plan.accepted = False
        plan.reject_reason = "retest_backstop_unaffordable"
        engine.notes["retest_backstop_unaffordable"] += 1
    else:
        engine.retest_backstop = backstop
    return plan


def maybe_add(self, book, leg, obs, now):
    if not self.book.get("banked_retest") or self.leg_member[leg.id] != MEMBER:
        return ADD(self, book, leg, obs, now)


@contextmanager
def dispatch():
    assert T._planner is PLAN and T.maybe_add is ADD
    T._planner, T.maybe_add = planner, maybe_add
    try:
        yield
    finally:
        T._planner, T.maybe_add = PLAN, ADD


def book_for_run():
    model = copy.deepcopy(r.books()["N11T"])
    model.update(label=f"N12|{NAME}", banked_retest=True)
    assert model["members"][3]["name"] == "TPB"
    model["members"].append(copy.deepcopy(model["members"][3]))
    return model


def main():
    freeze = HERE / "round27-freeze.json"
    cfg = json.loads(freeze.read_bytes())
    assert cfg == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{freeze.relative_to(r.ROOT).as_posix()}"], cwd=r.ROOT))
    for name, expected in cfg["source"].items():
        assert hashlib.sha256((HERE / name).read_text(encoding="utf-8").encode()).hexdigest() == expected
    model = book_for_run()
    assert cfg["book"] == json.loads(json.dumps(model))
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
    with dispatch(), Y.ROUTER.dispatch():
        result = RetestReplay(Y.dataset("year"), model, Y.table("year"), "year").run(*r.WINDOW)
    for row in result["trades"]:
        row.setdefault("status", "CLOSED" if row.get("net_pnl") is not None else "UNRESOLVED")
    out = {name: r.metrics(raw) for name, raw in {**controls, NAME: result}.items()}
    out["extra_trades"] = [t for t in result["trades"] if t.get("member") == MEMBER]
    with (HERE / f"round27-{r.YEAR}.json").open("x", encoding="utf-8") as handle:
        json.dump(out, handle, sort_keys=True, indent=2, default=str)
        handle.write("\n")
    value = out[NAME]
    print(r.YEAR, NAME, value["net"], value["unresolved"],
          {k: v for k, v in value["notes"].items() if k.startswith("retest_")}, flush=True)


if __name__ == "__main__":
    main()
