"""N012 round seven. Local acceptance in a low daily ADX regime."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess

import pandas as pd

import round1 as r
from config import settings
from fno_engine_mom import MomSignal

HERE = Path(__file__).resolve().parent
ENTRY = r.Y.BookReplay._entry
ROUTE = r.Y.BookReplay.route


def books():
    base = r.books()["N11T"]
    return {key: {**copy.deepcopy(base), "label": f"N12|{key}", "n12": key}
            for key in ("ACCEPT_CALL", "ACCEPT_NO_PUT")}


def opening_bullish(frame, now, bar):
    minute = now.hour * 60 + now.minute
    if not 595 <= minute < 705 or not bar:
        return False
    stamp = pd.Timestamp(bar)
    today = stamp.normalize()
    start = today + pd.Timedelta(hours=9, minutes=15)
    first = frame.loc[start:start + pd.Timedelta(minutes=25)]
    recent = frame.loc[stamp - pd.Timedelta(minutes=5):stamp]
    if len(first) != 6 or len(recent) != 2:
        return False
    high, low = float(first.high.max()), float(first.low.min())
    width = high - low
    if width <= 0 or float(first.close.iloc[-1] - first.open.iloc[0]) < .70 * width:
        return False
    if float(recent.close.min()) < low + .75 * width:
        return False
    earlier = frame.loc[:today - pd.Timedelta(minutes=1)]
    if earlier.empty:
        return False
    prior_end = earlier.index[-1]
    if prior_end.hour * 60 + prior_end.minute < 925:
        return False
    if float(recent.close.min()) <= float(earlier.close.iloc[-1]):
        return False
    times = earlier.index.hour * 60 + earlier.index.minute
    prior = earlier.loc[(times >= 555) & (times <= 580)]
    ranges = prior.groupby(prior.index.normalize()).agg(
        count=("close", "size"), high=("high", "max"), low=("low", "min"),
    )
    complete = ranges.loc[ranges["count"] == 6].tail(15)
    return len(complete) >= 10 and width >= .9 * float((complete.high - complete.low).median())


def entry(self, book, obs, frame, day, now):
    if self.book.get("n12") != "ACCEPT_CALL":
        return ENTRY(self, book, obs, frame, day, now)
    self.n12_book = book
    self.n12_new_call = False
    before = book.next_id
    try:
        result = ENTRY(self, book, obs, frame, day, now)
        if self.n12_new_call and book.next_id > before:
            self.n12_call_date = now.date()
            self.notes["n12_accept_call_admitted"] += 1
        return result
    finally:
        self.n12_book = None


def route(self, frame, regime, now):
    sig = ROUTE(self, frame, regime, now)
    mode = self.book.get("n12")
    if mode == "ACCEPT_NO_PUT" and self._fired == 4 and sig.direction is not None:
        if sig.direction.value == "SHORT" and opening_bullish(frame, now, sig.bar_ts):
            self.notes["n12_accept_put_filtered_tick"] += 1
            return MomSignal(bar_ts=sig.bar_ts, reject_reason="n12:opening_bullish")
    if mode != "ACCEPT_CALL" or sig.reject_reason != "n08:low_direction":
        return sig
    if self.n12_book.open or getattr(self, "n12_call_date", None) == now.date():
        return sig
    if not opening_bullish(frame, now, sig.bar_ts):
        return sig
    if r.f.L.R.stand_aside(r.f.L.vol_at(now, .9), r.f.L.paper_before(now), 20):
        return sig
    call = self._signal(4, frame, regime, now, sig.bar_ts)
    if call.direction is None or call.direction.value != "LONG":
        return sig
    self._fired = 4
    self._n02_decision = {
        "selected_profile": self.book["n02_profile"], "selector_policy": "STATIC",
        "selection_asof": None, "signal_bar": call.bar_ts, "selection_latest_label_exit": None,
        "origin": "N12_ACCEPT_CALL", "entry_expert": "TPB", "entry_gate": self.members[4]["gate"],
    }
    settings.FNO_MAX_LOTS = min(settings.FNO_MAX_LOTS, 1)
    settings.FNO_MAX_LOTS_PROVEN = min(settings.FNO_MAX_LOTS_PROVEN, 1)
    self.n12_new_call = True
    return call


r.Y.BookReplay._entry = entry
r.Y.BookReplay.route = route


def main():
    spec = HERE / "round7-freeze.json"
    rel = spec.relative_to(r.ROOT).as_posix()
    cfg = json.loads(spec.read_bytes())
    assert cfg == json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=r.ROOT))
    assert all(hashlib.sha256((HERE / name).read_bytes()).hexdigest() == sha for name, sha in cfg["files"].items())
    r.verify_freeze()
    variants = books()
    r.f.Z.N.run_books(variants, 2)
    out = {key: r.metrics(r.raw_for(book)) for key, book in variants.items()}
    for key, row in out.items():
        print(r.YEAR, key, row["net"], row["closed"], row["worst_day"], row["drawdown_pct"],
              {k: v for k, v in row["notes"].items() if k.startswith("n12")}, flush=True)
    with (HERE / f"round7-{r.YEAR}.json").open("x", encoding="utf-8") as file:
        json.dump(out, file, indent=2, sort_keys=True)
        file.write("\n")


if __name__ == "__main__":
    main()
