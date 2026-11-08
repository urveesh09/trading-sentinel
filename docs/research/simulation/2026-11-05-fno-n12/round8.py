"""N012 round eight. Use completed U.S. cash-market closes in two early setups."""
from bisect import bisect_left
import copy
import csv
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess

import pandas as pd

import round1 as r
from config import settings
from fno_engine_mom import FnoDirection, MomSignal

HERE = Path(__file__).resolve().parent
ENTRY = r.Y.BookReplay._entry
ROUTE = r.Y.BookReplay.route


def books():
    base = r.books()["N11T"]
    out = {}
    for mode in ("TRANSMISSION", "ABSORPTION"):
        book = copy.deepcopy(base)
        book.update(label=f"N12|{mode}", n12=mode)
        book["members"].append(copy.deepcopy(book["members"][3]))
        out[mode] = book
    return out


@lru_cache(maxsize=1)
def global_closes():
    def load(key):
        with (HERE / f"_local/{key}-2020-2026.csv").open(encoding="utf-8-sig", newline="") as file:
            rows = {r["observation_date"]: float(r[key]) for r in csv.DictReader(file) if r[key] not in ("", ".")}
        return rows

    nasdaq, vix = load("NASDAQCOM"), load("VIXCLS")
    common = sorted(nasdaq.keys() & vix.keys())
    returns, vix_moves = [], []
    for previous, current in zip(common, common[1:]):
        returns.append(nasdaq[current] / nasdaq[previous] - 1)
        vix_moves.append(vix[current] - vix[previous])
    return common[1:], returns, vix_moves


@lru_cache(maxsize=1500)
def global_side(day):
    days, returns, vix_moves = global_closes()
    latest = bisect_left(days, day.isoformat()) - 1
    if latest < 60 or (pd.Timestamp(day) - pd.Timestamp(days[latest])).days > 4:
        return 0
    before = sorted(abs(x) for x in returns[latest - 60:latest])
    current, vol = returns[latest], vix_moves[latest]
    if abs(current) < max(.008, before[47]) or abs(vol) < .6 or current * vol >= 0:
        return 0
    return 1 if current > 0 else -1


def setup(mode, frame, now):
    minute = now.hour * 60 + now.minute
    if not 600 <= minute < 700:
        return None
    external = global_side(now.date())
    if not external:
        return None
    bar = r.Y.replay._last_closed_bar(frame, now)
    if not bar:
        return None
    stamp = pd.Timestamp(bar)
    today = frame.loc[stamp.normalize():stamp]
    start = stamp.normalize() + pd.Timedelta(hours=9, minutes=15)
    if len(today) < 9 or today.index[0] != start or len(today) != 1 + (stamp - start).seconds // 300:
        return None
    earlier = frame.loc[:stamp.normalize() - pd.Timedelta(minutes=1)]
    if earlier.empty:
        return None
    previous = earlier.loc[earlier.index[-1].normalize():]
    if len(previous) < 72 or previous.index[-1].hour * 60 + previous.index[-1].minute < 925:
        return None
    first = today.iloc[:6]
    recent = today.iloc[-3:]
    highs, lows, closes = (today[k].to_list() for k in ("high", "low", "close"))
    atr = sum(max(h - l, abs(h - p), abs(l - p)) for h, l, p in
              zip(highs[-6:], lows[-6:], closes[-7:-1])) / 6
    high, low = float(first.high.max()), float(first.low.min())
    opening, last = float(first.open.iloc[0]), float(recent.close.iloc[-1])
    width = high - low
    prev_close = float(previous.close.iloc[-1])
    if width <= 0 or atr <= 0:
        return None
    if mode == "TRANSMISSION":
        side = external
        if side * (float(first.close.iloc[-1]) - opening) < .60 * width:
            return None
        edge = high if side == 1 else low
        touch = float(recent.low.iloc[-2] if side == 1 else recent.high.iloc[-2])
        if not -.50 * atr <= side * (touch - edge) <= .25 * atr:
            return None
        if not 0 < side * (last - edge) <= .35 * width or side * (last - prev_close) <= 0:
            return None
        if side * (last - float(recent.close.iloc[-2])) <= 0:
            return None
    else:
        side = -external
        prev_width = float(previous.high.max() - previous.low.min())
        if prev_width <= 0 or external * (opening - prev_close) < .25 * prev_width:
            return None
        if external * (float(first.close.iloc[-1]) - prev_close) <= 0:
            return None
        if side * (float(recent.close.iloc[0]) - prev_close) > 0:
            return None
        if not all(side * (float(close) - prev_close) > 0 for close in recent.close.iloc[-2:]):
            return None
    adverse = float(recent.low.min() if side == 1 else recent.high.max())
    risk = side * (last - adverse) + .1 * atr
    if not .60 * atr <= risk <= 1.50 * atr:
        return None
    return MomSignal(
        bar_ts=bar, direction=FnoDirection.LONG if side == 1 else FnoDirection.SHORT,
        close=last, atr=atr, stop_underlying=last - side * risk,
        target_underlying=last + side * 2 * risk, strategy=f"N12_{mode}",
    )


def entry(self, book, obs, frame, day, now):
    if self.book.get("n12") not in ("TRANSMISSION", "ABSORPTION"):
        return ENTRY(self, book, obs, frame, day, now)
    self.n12_active_book = book
    before = book.next_id
    try:
        result = ENTRY(self, book, obs, frame, day, now)
        if book.next_id > before and self.leg_member.get(before) == 5:
            self.n12_new_day = now.date()
            self.notes["n12_global_admission"] += 1
        return result
    finally:
        self.n12_active_book = None


def route(self, frame, regime, now):
    original = ROUTE(self, frame, regime, now)
    mode = self.book.get("n12")
    if mode not in ("TRANSMISSION", "ABSORPTION") or original.direction is not None:
        return original
    if self.n12_active_book.open or getattr(self, "n12_new_day", None) == now.date():
        return original
    if r.f.L.R.stand_aside(r.f.L.vol_at(now, .9), r.f.L.paper_before(now), 20):
        return original
    signal = setup(mode, frame, now)
    if signal is None:
        return original
    self._fired = 5
    self._n02_decision = {
        "selected_profile": "N12", "selector_policy": "STATIC", "selection_asof": None,
        "signal_bar": signal.bar_ts, "selection_latest_label_exit": None,
        "origin": "N12_GLOBAL", "entry_expert": mode, "entry_gate": "FLAT",
    }
    settings.FNO_MAX_LOTS = min(settings.FNO_MAX_LOTS, 1)
    settings.FNO_MAX_LOTS_PROVEN = min(settings.FNO_MAX_LOTS_PROVEN, 1)
    self.notes["n12_global_signal_ticks"] += 1
    return signal


r.Y.BookReplay._entry = entry
r.Y.BookReplay.route = route


def main():
    spec = HERE / "round8-freeze.json"
    rel = spec.relative_to(r.ROOT).as_posix()
    cfg = json.loads(spec.read_bytes())
    assert cfg == json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=r.ROOT))
    assert all(hashlib.sha256((HERE / name).read_bytes()).hexdigest() == sha for name, sha in cfg["files"].items())
    r.verify_freeze()
    variants = books()
    r.f.Z.N.run_books(variants, 2)
    out = {k: r.metrics(r.raw_for(b)) for k, b in variants.items()}
    for key, row in out.items():
        print(r.YEAR, key, row["net"], row["closed"], row["worst_day"],
              row["notes"].get("n12_global_admission", 0), flush=True)
    with (HERE / f"round8-{r.YEAR}.json").open("x", encoding="utf-8") as file:
        json.dump(out, file, indent=2, sort_keys=True)
        file.write("\n")


if __name__ == "__main__":
    main()
