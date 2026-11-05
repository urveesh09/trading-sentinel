"""Shared regular F&O book with one bounded follow-through after a native loss."""
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
NAME = "STOP_BREAK"
Y = r.Y
T = r.f.T
ENTRY = Y.BookReplay._entry
ROUTE = Y.BookReplay.route
ADD = T.maybe_add
PLAN = T._planner


def candidate(stopped, frame, now, future):
    exit_at = pd.Timestamp(datetime.fromisoformat(stopped["exit_time"]).replace(tzinfo=None))
    bar_ts = Y.replay._last_closed_bar(frame, now)
    if bar_ts is None:
        return None
    stamp = pd.Timestamp(bar_ts)
    start = exit_at.floor("5min") + pd.Timedelta(minutes=5)
    if stamp != start:
        return None
    expected = pd.date_range(end=stamp, periods=7, freq="5min")
    if expected[0].date() != now.date() or not expected.isin(frame.index).all():
        return None
    recent = frame.loc[expected]
    high, low, close = [recent[key].to_list() for key in ("high", "low", "close")]
    atr = sum(max(hi - lo, abs(hi - prev), abs(lo - prev))
              for hi, lo, prev in zip(high[1:], low[1:], close)) / 6
    side = -1 if stopped["direction"] == "LONG" else 1
    edge = max(high[-4:-1]) if side == 1 else min(low[-4:-1])
    boundary = side * max(side * edge, side * float(stopped["stop_underlying"]))
    width = high[-1] - low[-1]
    body = side * (close[-1] - float(recent.open.iloc[-1]))
    if atr <= 0 or width <= 0 or body < .5 * width:
        return None
    if side * (close[-1] - boundary) < .10 * atr or side * (future - boundary) <= 0:
        return None
    stop = boundary - side * .15 * atr
    risk = side * (future - stop)
    if not .35 * atr <= risk <= 1.5 * atr:
        return None
    return MomSignal(bar_ts=bar_ts, direction=FnoDirection.LONG if side == 1 else FnoDirection.SHORT,
                     close=close[-1], atr=atr, stop_underlying=stop,
                     target_underlying=future + side * 2.0 * risk, strategy=NAME)


def entry(self, book, obs, frame, day, now):
    if self.book.get("n12") != NAME:
        return ENTRY(self, book, obs, frame, day, now)
    self.reversal_context = book, obs.future.ltp
    self.reversal_limit = self.reversal_backstop = None
    before = book.next_id
    try:
        result = ENTRY(self, book, obs, frame, day, now)
        if book.next_id > before and self.leg_member[before] == 5:
            leg = book.open[before]
            assert leg.lots == 1 and self.reversal_backstop is not None
            leg.premium_stop = max(leg.premium_stop, self.reversal_backstop)
            self.notes["stop_break_admitted"] += 1
        return result
    finally:
        self.reversal_context = None


def route(self, frame, regime, now):
    native = ROUTE(self, frame, regime, now)
    if self.book.get("n12") != NAME or native.direction is not None:
        return native
    if not 600 <= now.hour * 60 + now.minute < 810 or getattr(self, "reversal_day", None) == now.date():
        return native
    book, future = self.reversal_context
    if book.open or not book.trades:
        return native
    stopped = book.trades[-1]
    if (stopped.get("exit_time", "")[:10] != now.date().isoformat()
            or stopped.get("exit_reason") != "underlying_stop" or stopped.get("net_pnl", 0) >= 0
            or stopped.get("member") == 5):
        return native
    signal = candidate(stopped, frame, now, future)
    if signal is None:
        return native
    self.reversal_day = now.date()
    self.notes["stop_break_confirmation"] += 1
    if r.f.L.R.stand_aside(r.f.L.vol_at(now, .9), r.f.L.paper_before(now), 20):
        self.notes["stop_break_stand_aside"] += 1
        return native
    self.reversal_limit = min(2000., 4000. + r.f.L.realised_today(book, now))
    if self.reversal_limit <= 0:
        self.notes["stop_break_no_day_room"] += 1
        return native
    self._fired = 5
    self._n02_decision = {"selected_profile": "N12", "selector_policy": "STATIC", "selection_asof": None,
                          "signal_bar": signal.bar_ts, "selection_latest_label_exit": None,
                          "origin": NAME, "entry_expert": NAME, "entry_gate": "AFTER_STOP"}
    settings.FNO_MAX_LOTS = min(settings.FNO_MAX_LOTS, 1)
    settings.FNO_MAX_LOTS_PROVEN = min(settings.FNO_MAX_LOTS_PROVEN, 1)
    return signal


def planner(sig, snap, regime, now, state):
    plan = PLAN(sig, snap, regime, now, state)
    if sig.strategy != NAME:
        return plan
    engine = T.ENGINE["now"]
    if not plan.accepted:
        engine.notes[f"stop_break_refusal:{plan.reject_reason}"] += 1
        return plan
    extra = T.R.extra_cost(engine.book.get("cost"), plan.lots)
    points = backstop_points(engine.reversal_limit, plan.quote.ask, plan.lot_size, extra, calc_fno_costs)
    backstop = stop_price(plan.quote.ask, points) if points is not None else None
    if backstop is None or backstop >= plan.quote.bid:
        plan.accepted = False
        plan.reject_reason = "stop_break_backstop_unaffordable"
        engine.notes["stop_break_backstop_unaffordable"] += 1
    else:
        engine.reversal_backstop = backstop
    return plan


def maybe_add(self, book, leg, obs, now):
    if self.book.get("n12") != NAME or self.leg_member[leg.id] != 5:
        return ADD(self, book, leg, obs, now)


def book_for_run():
    book = copy.deepcopy(r.books()["N11T"])
    book.update(label="N12|STOP_BREAK", n12=NAME)
    book["members"].append(copy.deepcopy(book["members"][3]))
    return book


Y.BookReplay._entry = entry
Y.BookReplay.route = route
T._planner = planner
T.maybe_add = maybe_add


def verify():
    spec = HERE / "round15-freeze.json"
    cfg = json.loads(spec.read_bytes())
    assert cfg == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{spec.relative_to(r.ROOT).as_posix()}"], cwd=r.ROOT))
    for name, sha in cfg["files"].items():
        assert hashlib.sha256((HERE / name).read_text(encoding="utf-8").encode()).hexdigest() == sha, name
    assert cfg["book"] == json.loads(json.dumps(book_for_run())), "book differs from freeze"
    assert cfg["windows"][r.YEAR] == list(r.WINDOW)
    r.verify_freeze()
    dataset = r.DATASETS[r.YEAR]
    manifest = json.loads((dataset / "manifest.json").read_bytes())
    with (dataset / "breeze.sqlite").open("rb") as handle:
        assert hashlib.file_digest(handle, "sha256").hexdigest() == manifest["files_sha256"]["breeze.sqlite"]


def main():
    verify()
    controls = {name: r.raw_for(r.books()[name]) for name in ("N11", "N11T")}
    for name, raw in controls.items():
        assert r.money(raw) == r.money(trades(r.YEAR, name)[1]), name
    selected = book_for_run()
    r.f.Z.N.run_books({NAME: selected}, 1)
    raw = r.raw_for(selected)
    out = {name: r.metrics(data) for name, data in {**controls, NAME: raw}.items()}
    out["reversals"] = [t for t in raw["trades"] if t.get("member") == 5]
    with (HERE / f"round15-{r.YEAR}.json").open("x", encoding="utf-8") as file:
        json.dump(out, file, indent=2, sort_keys=True, default=str)
        file.write("\n")
    row = out[NAME]
    print(r.YEAR, row["net"], row["worst_day"], row["drawdown_pct"],
          {k: v for k, v in row["notes"].items() if k.startswith("stop_break")}, flush=True)


if __name__ == "__main__":
    main()
