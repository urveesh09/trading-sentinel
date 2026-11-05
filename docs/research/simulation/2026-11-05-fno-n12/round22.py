"""Funded 15-minute auction acceptance and rejection in separate N11T accounts."""
from contextlib import closing
import copy
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import subprocess

from anatomy import trades
import round1 as r
from config import settings
from fno_engine_mom import FnoDirection, MomSignal

HERE = Path(__file__).resolve().parent
Y = r.Y
T = r.f.T
ADD = T.maybe_add
ACCEPT, REJECT = "ACCEPT_15", "REJECT_15"


@dataclass(frozen=True)
class Bar:
    opened: float
    high: float
    low: float
    close: float


def bars15(rows, start, boundary):
    minute_count = int((boundary - start).total_seconds() // 60)
    if not minute_count or minute_count % 15 or len(rows) != minute_count:
        return None
    for i, (at, opened, high, low, close) in enumerate(rows):
        if at != (start + timedelta(minutes=i)).isoformat(sep=" ") or not 0 < low <= min(opened, close) <= max(opened, close) <= high:
            return None
    out = []
    for i in range(0, minute_count, 15):
        window = rows[i:i+15]
        out.append(Bar(window[0][1], max(row[2] for row in window), min(row[3] for row in window), window[-1][4]))
    return out


def risk_atr(bars):
    recent = bars[-4:]
    preceding = [bars[-5].close if len(bars) > 4 else recent[0].opened, *(bar.close for bar in recent[:-1])]
    return sum(max(bar.high - bar.low, abs(bar.high - prior), abs(bar.low - prior))
               for bar, prior in zip(recent, preceding)) / 4.


def levels(bars, future, mode):
    if len(bars) < 4 or (mode == ACCEPT and len(bars) < 5):
        return None
    low, high = min(bar.low for bar in bars[:3]), max(bar.high for bar in bars[:3])
    width, atr = high - low, risk_atr(bars)
    if min(width, atr) <= 0:
        return None
    earlier, last = bars[-2:]
    midpoint = (high + low) / 2.
    for break_side, edge in ((1, high), (-1, low)):
        if mode == ACCEPT:
            extreme = last.low if break_side > 0 else last.high
            retest = break_side * (extreme - edge)
            if not all(break_side * (bar.close - edge) >= .05 * width for bar in (earlier, last)):
                continue
            if not -.10 * width <= retest <= .10 * width or break_side * (future - edge) <= 0:
                continue
            side = break_side
            stop = extreme - side * .10 * atr
            target = future + 2. * (future - stop)
        else:
            if last.high > high and last.low < low:
                return None
            extreme = last.high if break_side > 0 else last.low
            if not low <= earlier.close <= high or break_side * (extreme - edge) < .10 * width:
                continue
            if break_side * (edge - last.close) < .10 * width or not low <= last.close <= high:
                continue
            if not low <= future <= high or break_side * (future - midpoint) <= 0:
                continue
            side = -break_side
            stop = extreme - side * .10 * atr
            target = midpoint
        risk = side * (future - stop)
        if .50 * atr <= risk <= 1.50 * atr and side * (target - future) >= 1.50 * risk:
            return side, stop, target, atr
    return None


class SlowReplay(Y.BookReplay):
    def _entry(self, book, obs, frame, day, now):
        self.auction_context = book, obs
        before = book.next_id
        try:
            result = super()._entry(book, obs, frame, day, now)
            if book.next_id > before and self.leg_member[before] == 5:
                assert book.open[before].lots == 1
                self.notes["auction_admitted"] += 1
            return result
        finally:
            self.auction_context = None

    def route(self, frame, regime, now):
        native = super().route(frame, regime, now)
        minute = now.hour * 60 + now.minute
        if native.direction is not None or not 615 <= minute <= 750 or minute % 15:
            return native
        if getattr(self, "auction_day", None) == now.date():
            return native
        book, obs = self.auction_context
        if book.open or regime == "REGIME_3_CRISIS" or now.date() in self.data.option_expiries()[0]:
            return native
        if r.f.L.R.stand_aside(r.f.L.vol_at(now, .9), r.f.L.paper_before(now), 20):
            return native
        boundary = now.replace(tzinfo=None, second=0, microsecond=0)
        start = boundary.replace(hour=9, minute=15)
        rows = self.raw.execute(
            "SELECT datetime,open,high,low,close FROM candles WHERE kind='future' AND expiry=? "
            "AND strike=0 AND opt='' AND datetime>=? AND datetime<? ORDER BY datetime",
            (obs.future.contract.expiry.isoformat(), start.isoformat(sep=" "), boundary.isoformat(sep=" ")),
        ).fetchall()
        bars = bars15(rows, start, boundary)
        if bars is None:
            self.notes["auction_incomplete_clock"] += 1
            return native
        mode = self.book["n12_auction"]
        trade = levels(bars, obs.future.ltp, mode)
        bar_ts = Y.replay._last_closed_bar(frame, now)
        if trade is None or bar_ts is None:
            return native
        side, stop, target, atr = trade
        self.auction_day = now.date()
        self._fired = 5
        self._n02_decision = {"selected_profile": "N12", "selector_policy": "STATIC", "selection_asof": None,
                              "signal_bar": bar_ts, "selection_latest_label_exit": None,
                              "origin": mode, "entry_expert": mode, "entry_gate": "FLAT"}
        settings.FNO_MAX_LOTS = min(settings.FNO_MAX_LOTS, 1)
        settings.FNO_MAX_LOTS_PROVEN = min(settings.FNO_MAX_LOTS_PROVEN, 1)
        self.notes["auction_planner_attempt"] += 1
        return MomSignal(bar_ts=bar_ts, direction=FnoDirection.LONG if side == 1 else FnoDirection.SHORT,
                         close=bars[-1].close, atr=atr, stop_underlying=stop, target_underlying=target, strategy=mode)

    def run(self, start, end):
        with closing(self.data._connect()) as self.raw:
            return super().run(start, end)


def maybe_add(self, book, leg, obs, now):
    if self.book.get("n12_auction") is None or self.leg_member[leg.id] != 5:
        return ADD(self, book, leg, obs, now)


def books():
    selected = {}
    for name in (ACCEPT, REJECT):
        model = copy.deepcopy(r.books()["N11T"])
        model.update(label="N12|" + name, n12_auction=name)
        model["members"].append(copy.deepcopy(model["members"][3]))
        selected[name] = model
    return selected


T.maybe_add = maybe_add


def main():
    freeze = HERE / "round22-freeze.json"
    cfg = json.loads(freeze.read_bytes())
    assert cfg == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{freeze.relative_to(r.ROOT).as_posix()}"], cwd=r.ROOT))
    for name, expected in cfg["source"].items():
        assert hashlib.sha256((HERE / name).read_text(encoding="utf-8").encode()).hexdigest() == expected
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
            engine = SlowReplay(Y.dataset("year"), model, Y.table("year"), "year")
            results[name] = engine.run(*r.WINDOW)
        for row in results[name]["trades"]:
            row.setdefault("status", "CLOSED" if row.get("net_pnl") is not None else "UNRESOLVED")
    out = {name: r.metrics(raw) for name, raw in {**controls, **results}.items()}
    out["extra_trades"] = {name: [t for t in raw["trades"] if t.get("member") == 5] for name, raw in results.items()}
    with (HERE / f"round22-{r.YEAR}.json").open("x", encoding="utf-8") as handle:
        json.dump(out, handle, sort_keys=True, indent=2, default=str)
        handle.write("\n")
    for name in results:
        value = out[name]
        print(r.YEAR, name, value["net"], value["worst_day"],
              {k: v for k, v in value["notes"].items() if k.startswith("auction_")}, flush=True)


if __name__ == "__main__":
    main()
