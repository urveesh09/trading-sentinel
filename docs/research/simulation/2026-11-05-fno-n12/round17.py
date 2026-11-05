"""Replace the pooled low-volatility reading only when matched paper evidence is strong."""
from collections import defaultdict
import copy
from datetime import timedelta
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, stdev
import subprocess

from anatomy import trades
import round1 as r
from config import settings
from fno_engine_mom import MomSignal

HERE = Path(__file__).resolve().parent
Y = r.Y
ROUTE = Y.BookReplay.route
ENTRY = Y.BookReplay._entry
ARMS = ("CONTEXT_RELEASE", "CONTEXT_GATE")


@lru_cache(maxsize=1)
def shadow_rows():
    out = []
    for at, trade in r.f.L.U.paper_rows():
        assert at.tzinfo is not None and trade["entry_qty"] == 65
        net = float(trade["net_pnl"])
        assert math.isfinite(net)
        out.append((at, trade["entry_expert"], trade["direction"], net))
    return tuple(out)


def shadow_digest():
    data = [(at.isoformat(), expert, side, net) for at, expert, side, net in shadow_rows()]
    return hashlib.sha256(json.dumps(data, separators=(",", ":")).encode()).hexdigest()


def rating(rows, day, expert, side):
    first = day - timedelta(days=180)
    dates = defaultdict(list)
    for at, family, direction, net in rows:
        if first <= at.date() < day and (family, direction) == (expert, side):
            dates[at.date()].append(net)
    if len(dates) < 8:
        return 0
    points = [max(-2500., min(2500., mean(dates[d]))) for d in sorted(dates)[-20:]]
    average, error = mean(points), stdev(points) / math.sqrt(len(points))
    if average - error > 200.:
        return 1
    if average + error < -200.:
        return -1
    return 0


@lru_cache(maxsize=8192)
def prior_rating(day, expert, side):
    return rating(shadow_rows(), day, expert, side)


def gate(native_hold, context, mode):
    if context > 0 and native_hold:
        return "RELEASE"
    if context < 0 and not native_hold and mode == "CONTEXT_GATE":
        return "HOLD"
    return "NATIVE_HOLD" if native_hold else "NATIVE_ALLOW"


def route(self, frame, regime, now):
    mode = self.book.get("n12")
    if mode not in ARMS:
        return ROUTE(self, frame, regime, now)
    cfg = self.book["n11"]
    need = cfg["stand"]
    above = r.f.L.vol_at(now, float(cfg["stand_ratio"]))
    if above:
        return ROUTE(self, frame, regime, now)
    cfg["stand"] = None
    try:
        signal = ROUTE(self, frame, regime, now)
    finally:
        cfg["stand"] = need
    if signal.direction is None:
        return signal
    native_hold = r.f.L.R.stand_aside(above, r.f.L.paper_before(now), need)
    expert = self._n02_decision["entry_expert"]
    context = prior_rating(now.date(), expert, signal.direction.value)
    action = gate(native_hold, context, mode)
    if action in ("HOLD", "RELEASE"):
        if self.context_last_changed != (action, signal.bar_ts):
            self.notes[f"context_{action.lower()}_bars"] += 1
            self.context_last_changed = action, signal.bar_ts
    if action == "RELEASE":
        settings.FNO_MAX_LOTS = min(1, settings.FNO_MAX_LOTS)
        settings.FNO_MAX_LOTS_PROVEN = min(1, settings.FNO_MAX_LOTS_PROVEN)
        self.context_released = True
    if action == "HOLD":
        return MomSignal(bar_ts=signal.bar_ts, reject_reason="n12:context_hold")
    if action == "NATIVE_HOLD":
        self.notes["n11_stood_aside"] += 1
        return MomSignal(bar_ts=signal.bar_ts, reject_reason="n11:stand_aside")
    return signal


def entry(self, book, obs, frame, day, now):
    if self.book.get("n12") not in ARMS:
        return ENTRY(self, book, obs, frame, day, now)
    self.context_released = False
    if not hasattr(self, "context_last_changed"):
        self.context_last_changed = None
    before = book.next_id
    result = ENTRY(self, book, obs, frame, day, now)
    if self.context_released and book.next_id > before:
        assert book.open[before].lots == 1
        self.notes["context_release_admitted"] += 1
    return result


def books():
    base = r.books()["N11T"]
    return {arm: {**copy.deepcopy(base), "label": "N12|" + arm, "n12": arm} for arm in ARMS}


Y.BookReplay.route = route
Y.BookReplay._entry = entry


def verify():
    spec = HERE / "round17-freeze.json"
    cfg = json.loads(spec.read_bytes())
    assert cfg == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{spec.relative_to(r.ROOT).as_posix()}"], cwd=r.ROOT))
    for name, sha in cfg["files"].items():
        assert hashlib.sha256((HERE / name).read_text(encoding="utf-8").encode()).hexdigest() == sha, name
    assert cfg["books"] == json.loads(json.dumps(books()))
    assert cfg["shadow"]["2022" if r.YEAR == "2022" else "2023_2026"] == shadow_digest()
    assert cfg["windows"][r.YEAR] == list(r.WINDOW)
    r.verify_freeze()
    dataset = r.DATASETS[r.YEAR]
    manifest = json.loads((dataset / "manifest.json").read_bytes())
    with (dataset / "breeze.sqlite").open("rb") as handle:
        assert hashlib.file_digest(handle, "sha256").hexdigest() == manifest["files_sha256"]["breeze.sqlite"]


def changed_entries(raw, baseline):
    def index(data):
        return {(t["entry_time"], t["tradingsymbol"]): t for t in data["trades"]}

    current, prior = index(raw), index(baseline)
    return {"candidate_only": [current[k] for k in sorted(current.keys() - prior.keys())],
            "control_only": [prior[k] for k in sorted(prior.keys() - current.keys())]}


def main():
    verify()
    controls = {name: r.raw_for(r.books()[name]) for name in ("N11", "N11T")}
    for name, raw in controls.items():
        assert r.money(raw) == r.money(trades(r.YEAR, name)[1]), name
    candidates = books()
    r.f.Z.N.run_books(candidates, 2)
    results = {arm: r.raw_for(book) for arm, book in candidates.items()}
    out = {name: r.metrics(raw) for name, raw in {**controls, **results}.items()}
    out["changed_entries"] = {arm: changed_entries(raw, controls["N11T"]) for arm, raw in results.items()}
    with (HERE / f"round17-{r.YEAR}.json").open("x", encoding="utf-8") as file:
        json.dump(out, file, indent=2, sort_keys=True, default=str)
        file.write("\n")
    for arm in ARMS:
        row = out[arm]
        print(r.YEAR, arm, row["net"], row["worst_day"], row["drawdown_pct"],
              {k: v for k, v in row["notes"].items() if k.startswith("context_")}, flush=True)


if __name__ == "__main__":
    main()
