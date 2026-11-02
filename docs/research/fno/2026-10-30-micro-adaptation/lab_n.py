"""O30n: bounded micro-adaptive offspring of the robust pullback family.

Research only. Eight declared candidates, not an unbounded genetic search.
2025/2026 are development data; 2024 and forward sessions are never read here.
Owner asks for macro + micro decisions, new generations and honest testing.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path.insert(0, str(ROOT / "docs/research/fno/2026-10-30-case-study"))
import lab_c as C

Y, G, O27F = C.Y, C.G, C.O27F
LOCAL = HERE / "_local"
Y.EVALS = LOCAL / "evals"
Y.GUARD.update(min_free_gb_market=3.0, min_free_gb_after=2.0, market_jobs=2)
FAMILY = "VWAP_RECLAIM_N"
_ENTRIES = {}


def entries(m, f):
    """Confirmed VWAP pullback reclaim, max one entry per direction/session.

    Previous bar touches VWAP; latest close clears previous high/low, is
    on the EMA20 trend side, and VWAP slopes in that direction over 3 bars.
    First possible decision 09:45, last 14:00. All comparisons causal.
    """
    key = (O27F._key(f["t"], f["day"]), Y.digest(m))
    if key in _ENTRIES:
        return _ENTRIES[key]
    t, out, done = f["t"], {}, set()
    for i in range(5, len(t)):
        r, p, old = t.iloc[i], t.iloc[i - 1], t.iloc[i - 3]
        if not 585 <= r["minute"] + 5 <= 840:
            continue
        for d in (1, -1):
            touch = p["low"] <= p["vwap"] if d == 1 else p["high"] >= p["vwap"]
            cleared = r["close"] > p["high"] if d == 1 else r["close"] < p["low"]
            if d not in done and touch and cleared and d * (r["close"] - r["ema20"]) > 0 \
                    and d * (r["close"] - r["vwap"]) > 0 and d * (r["vwap"] - old["vwap"]) > 0:
                out[f["stamps"][i]] = d
                done.add(d)
    _ENTRIES[key] = out
    if len(_ENTRIES) > 600:
        _ENTRIES.pop(next(iter(_ENTRIES)))
    return out


_signal_before = G.new_signal


def new_signal(m, frame, regime, now):
    if m["family"] != FAMILY:
        return _signal_before(m, frame, regime, now)
    f = O27F.day_features(frame, now.date())
    stamp = O27F.last_closed_bar(f, now) if f else None
    if not stamp or not f["complete_open"]:
        return G.MomSignal(bar_ts=stamp or "", reject_reason="reclaim:no_features")
    return G._signal(frame, regime, now, m, entries(m, f).get(stamp), stamp, f)


G.new_signal = new_signal


def micro_state(leg, frame, now):
    """Only completed five-minute bars of today's contract; no daily hindsight."""
    if frame is None:
        return False, False
    f = O27F.day_features(frame, now.date())
    if not f:
        return False, False
    t = f["t"]
    end = int(t.index.searchsorted(now.replace(tzinfo=None) - timedelta(minutes=5), side="right"))
    if end < 4:
        return False, False
    r, p, old = t.iloc[end - 1], t.iloc[end - 2], t.iloc[end - 4]
    direction = 1 if leg.direction == "LONG" else -1
    risk = abs(leg.entry_underlying - leg.stop_underlying)
    strong = (risk > 0 and direction * (r["close"] - leg.entry_underlying) >= 0.5 * risk
              and direction * (r["close"] - r["vwap"]) > 0
              and direction * (r["close"] - r["ema20"]) > 0
              and direction * (r["vwap"] - old["vwap"]) > 0 and r["er4"] >= 0.25)
    # Two consecutive post-entry closes beyond VWAP, never the entry candle.
    post_entry = C.replay._aware(leg.entry_time).replace(tzinfo=None) <= t.index[end - 2]
    broken = post_entry and direction * (r["close"] - r["vwap"]) < 0 \
        and direction * (p["close"] - p["vwap"]) < 0
    return bool(strong), bool(broken)


_manage_before = Y.BookReplay._manage


def manage(self, book, obs, now):
    mode = self.book.get("micro")
    if not mode:
        return _manage_before(self, book, obs, now)
    original = self.policies
    states = {k: micro_state(leg, self._frame, now) for k, leg in book.open.items()}
    policies = list(original)
    if mode in ("RUN", "BOTH"):
        for k, (strong, _) in states.items():
            if strong:
                i = self.leg_member[k]
                # Extend only while the thesis remains valid. Retain premium
                # backstop, profit lock, original stop and hard-flat deadline.
                overrides = {**dict(original[i].exit_overrides), "FNO_TIME_STOP_MIN": 120.0,
                             "FNO_TRAIL_ATR_MULT": 2.0}
                policies[i] = replace(original[i], exit_overrides=tuple(sorted(overrides.items())))
                self.notes["micro_strong_observations"] += 1
    try:
        self.policies = policies
        _manage_before(self, book, obs, now)  # shipped safety/deadline exits have priority
    finally:
        self.policies = original
    if mode not in ("BREAK", "BOTH"):
        return
    from fno_adaptive_risk import Close
    for k in list(book.open):
        if not states.get(k, (False, False))[1]:
            continue
        leg = book.open[k]
        quote = obs.options.get(leg.token)
        if quote is None or quote.bid <= 0:
            self.notes["micro_unpriced_no_bid"] += 1
            continue
        record, net = C.replay._close_record(leg, now, quote.bid, "micro_two_vwap_closes", obs.future.ltp)
        record.update(member=self.leg_member[k], entry_qty=leg.initial_qty)
        book.trades.append(record)
        book.equity += net
        book.closes.append((now, net, "SINGLE_LEG"))
        book.completed.append(Close(now, record["net_pnl"], True))
        del book.open[k]


Y.BookReplay._manage = manage


def books():
    live = C.book(C.four(lambda c: C.ADX))
    best = C.book(C.four(lambda c: "ALWAYS" if c == "TPB" else C.ADX))
    tpb = Y.book_of([Y.named("TPB")])
    reclaim = G.new_member(FAMILY, "ALWAYS", stop_atr=1.0, target_r=2.0, exit="LIVE")
    out = {"REF|LIVE": live, "REF|BEST": best, "REF|TPB": tpb}
    for mode in ("RUN", "BREAK", "BOTH"):
        for name, parent in (("TPB", tpb), ("BEST", best)):
            out[f"N|{name}|{mode}"] = {**parent, "micro": mode}
    out["N|RECLAIM"] = Y.book_of([reclaim])
    out["N|BEST+RECLAIM"] = {"members": [*best["members"], Y.canonical_member(reclaim)]}
    out.update({f"NULL{i:02d}": b for i, b in enumerate(Y.null_fixed())})
    return out


RULE = {
    "hypothesis": "intraday thesis renewal/invalidation improves robust pullback parents; confirmed reclaim adds entries",
    "candidates": 8, "seen_data": [2025, 2026], "untouched": "2024 existing exam unchanged; no 2024 access",
    "pass": "beats REF|BEST in EACH year; >=40 trades/year; >=3/4 halves not worse than REF|BEST; "
            "positive net minus Rs200/trade, positive without best day, drawdown <=1.25*REF|BEST each year; "
            "beats 20 null books median both years; no unresolved positions",
    "selection": "choose best candidate by worst half-year net minus 200/trade on ONE year, ties name; "
                 "must beat REF|BEST on OTHER year both ways. Reverse-year test is diagnostic, not chronological OOS",
    "honesty": "all 8 reported; no second search or changed rule after results; additional Rs300/trade stress; "
               "seen-year passes are research candidates only, not real-money qualification",
}


def bindings():
    b = C.year_bindings()
    for name in ("lab_n.py", "analyze_n.py", "test_lab_n.py"):
        p = HERE / name
        b["sources"][p.relative_to(ROOT).as_posix()] = Y.grid._sha(p)
    return b


def freeze():
    parts = {}
    for year in ("2025", "2026"):
        raw = subprocess.check_output([sys.executable, str(HERE / "lab_n.py"), "bindings"], cwd=ROOT,
                                      env={**os.environ, "O30C_YEAR": year})
        parts[year] = json.loads(raw.decode().strip().splitlines()[-1])
    Y.write_new(HERE / "freeze.json", {"schema": "o30n_micro_v1", "bindings": parts, "books": books(),
                                       "rule": RULE, "can_place_orders": False})
    print("FROZEN", len(books()), "books x 2 years")


def run(jobs):
    frozen = json.loads((HERE / "freeze.json").read_text())
    assert frozen["bindings"][C.YEAR] == json.loads(json.dumps(bindings(), default=str)), "inputs changed"
    rel = (HERE / "freeze.json").relative_to(ROOT).as_posix()
    assert frozen == json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)), "not committed"
    assert 1 <= jobs <= 2
    O27F.deny_network()
    all_books = books()
    Y.EVALS.mkdir(parents=True, exist_ok=True)
    dirs = [ROOT / f"docs/research/fno/{s}/_local/evals" for s in (
        "2026-10-30-day-router", "2026-10-30-case-study", "2026-10-30-nifty-2025-test",
        "2026-10-29-year-genome")]
    for n, b in all_books.items():
        if not n.startswith(("REF", "NULL")):
            continue
        key = Y.task_key(b, "year", C.WINDOW) + ".json"
        src = next((d / key for d in dirs if (d / key).is_file()), None)
        if src and not (Y.EVALS / key).exists():
            shutil.copyfile(src, Y.EVALS / key)
    C.table("year")
    with ProcessPoolExecutor(max_workers=jobs, initializer=C._init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(all_books.values()), source="year", window=C.WINDOW)
    Y.write_new(LOCAL / f"results-raw-{C.YEAR}.json", {"freeze_sha256": Y.grid._sha(HERE / "freeze.json"),
        "year": C.YEAR, "books": {n: Y.task_key(b, "year", C.WINDOW) for n, b in all_books.items()},
        "trades": runner.trades})
    print("DONE", C.YEAR, len(runner.trades), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["bindings", "freeze", "run"])
    cli.add_argument("--jobs", type=int, default=2)
    a = cli.parse_args()
    if a.action == "bindings":
        print(json.dumps(bindings(), default=str))
    else:
        {"freeze": freeze, "run": lambda: run(a.jobs)}[a.action]()
