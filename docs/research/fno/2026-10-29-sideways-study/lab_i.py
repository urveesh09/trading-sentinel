"""O29i sideways-day study - research only. No runtime module imports this file.

Owner (Oct 29, after O29h): "on the days in system is sideways ... search for the most best strategies at that time
... capital invested you can reduce ... test out strategies that are famous for sideways days".

On the days UNION_ADX sits out (yesterday's NIFTY daily ADX(14) < 25), four textbook range-day entries, each through
the same shipped book (O29f BookReplay via lab_g), gated to those days only:
  FADE        a failed opening-range break: a close beyond the 30- (or 20-) minute range, then within 2 bars a close
              back inside: buy the option the other way (stop at the failed extreme or 1 ATR);
  VWAP_REVERT a close outside VWAP +/- k session sigma, then a close back inside: back toward VWAP;
  PDL_FADE    a poke beyond yesterday's high (low) that closes back inside: the other way;
  RSI2        5-minute RSI(2) at an extreme (<= 5 / >= 95) and the next bar turning: the other way (10:00-14:30);
and 20 random-entry books on the same days as the luck yardstick. Results are read per lot (the real-money test
trades one lot; a smaller size on these days scales the same per-lot result down).
"""
from __future__ import annotations

import argparse
import itertools
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
WHY = ROOT / "docs/research/fno/2026-10-29-why-study"
sys.path[:0] = [str(WHY), str(HERE)]
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import lab_g as G  # noqa: E402  (O29g: patches the O29f book with NEW members and the regime table)

Y, O27F = G.Y, G.O27F
LOCAL = HERE / "_local"
Y.EVALS = LOCAL / "evals"
SIDEWAYS = "adx_abs25:LOW"
SIDE_FAMILIES = ("FADE", "VWAP_REVERT", "PDL_FADE", "RSI2")
GRID = {
    "FADE": {"level": ("OR30", "OR20"), "stop": ("STRUCT", 1.0), "target_r": (1.5, 2.4), "exit": ("LIVE", "LATE")},
    "VWAP_REVERT": {"k": (1.5, 2.0), "stop": (1.0, 1.5), "target_r": (1.5, 2.4), "exit": ("LIVE", "LATE")},
    "PDL_FADE": {"stop": (1.0, 1.5), "target_r": (1.5, 2.4), "exit": ("LIVE", "LATE")},
    "RSI2": {"stop": (1.0, 1.5), "target_r": (1.5, 2.4), "exit": ("LIVE", "LATE")},
}
_TABLES: dict = {}


def side_table(m: dict, f: dict) -> dict:
    """bar_ts -> (direction, stop) for one member on one session; bar i reads bars <= i only; one entry per side."""
    key = (G.digest(m), f["day"].isoformat(), f["stamps"][-1], len(f["stamps"]))
    if key in _TABLES:
        return _TABLES[key]
    t = f["t"]
    c, o, h, l = t["close"].values, t["open"].values, t["high"].values, t["low"].values
    atr, mins = t["atr"].values, t["minute"].values
    vwap, vsd = t["vwap"].values, t["vsd"].values
    out, done = {}, set()

    def put(i, d, stop):
        if d in done or not atr[i] > 0 or (c[i] - stop) * d <= 0:
            return
        out[f["stamps"][i]] = (d, float(stop))
        done.add(d)

    def atr_stop(i, d):
        return c[i] - d * float(m["stop"]) * atr[i]

    fam = m["family"]
    if fam == "FADE":
        n = 6 if m["level"] == "OR30" else 4
        if len(t) > n and mins[n - 1] == 555 + 5 * (n - 1):
            orh, orl = float(h[:n].max()), float(l[:n].min())
            for i in range(n + 1, len(t)):
                for d, level in ((-1, orh), (1, orl)):
                    broke = [j for j in range(max(n, i - 2), i) if (c[j] - level) * -d > 0]
                    if broke and (c[i] - level) * -d < 0 and (c[i - 1] - level) * -d > 0:
                        j0 = broke[0]
                        stop = (h[j0:i + 1].max() + 0.25 * atr[i]) if d < 0 else (l[j0:i + 1].min() - 0.25 * atr[i])
                        put(i, d, stop if m["stop"] == "STRUCT" else atr_stop(i, d))
    elif fam == "VWAP_REVERT":
        for i in range(1, len(t)):
            if mins[i] < 585 or not vsd[i] > 0:
                continue
            for d, sign in ((-1, 1), (1, -1)):
                band, prev = vwap[i] + sign * m["k"] * vsd[i], vwap[i - 1] + sign * m["k"] * vsd[i - 1]
                if (c[i - 1] - prev) * sign > 0 and (c[i] - band) * sign < 0:
                    put(i, d, atr_stop(i, d))
    elif fam == "PDL_FADE":
        pdh, pdl = f["pdh"], f["pdl"]
        for i in range(1, len(t)):
            if mins[i] < 585:
                continue
            if h[i] > pdh and c[i] < pdh and c[i - 1] <= pdh:
                put(i, -1, max(h[i] + 0.25 * atr[i], atr_stop(i, -1)) if m["stop"] == 1.0 else atr_stop(i, -1))
            if l[i] < pdl and c[i] > pdl and c[i - 1] >= pdl:
                put(i, 1, min(l[i] - 0.25 * atr[i], atr_stop(i, 1)) if m["stop"] == 1.0 else atr_stop(i, 1))
    elif fam == "RSI2":
        delta = np.diff(c, prepend=c[0])
        gain = pd.Series(np.clip(delta, 0, None)).ewm(alpha=0.5, adjust=False).mean().values
        loss = pd.Series(np.clip(-delta, 0, None)).ewm(alpha=0.5, adjust=False).mean().values
        rsi = np.where(loss > 0, 100 - 100 / (1 + gain / np.where(loss > 0, loss, 1)), 100.0)
        for i in range(2, len(t)):
            if not (600 <= mins[i] + 5 <= 870):
                continue
            if rsi[i - 1] <= 5 and c[i] > o[i]:
                put(i, 1, atr_stop(i, 1))
            if rsi[i - 1] >= 95 and c[i] < o[i]:
                put(i, -1, atr_stop(i, -1))
    else:
        raise ValueError(fam)
    _TABLES[key] = out
    while len(_TABLES) > 6000:
        _TABLES.pop(next(iter(_TABLES)))
    return out


def side_signal(m: dict, frame, regime: str, now):
    naive = now.replace(tzinfo=None)
    f = O27F.day_features(frame, naive.date())
    bar_ts = O27F.last_closed_bar(f, now) if f is not None else Y.replay._last_closed_bar(frame, now)
    if bar_ts is None or f is None or not f["complete_open"]:
        return G.MomSignal(bar_ts=bar_ts or "", reject_reason="side:no_features")
    hit = side_table(m, f).get(bar_ts)
    if hit is None:
        return G.MomSignal(bar_ts=bar_ts, reject_reason="side:no_trigger")
    d, stop = hit
    sig = G._signal(frame, regime, now, {**m, "stop_atr": 1.0}, d, bar_ts, f)
    if sig.direction is not None:
        risk = abs(sig.close - stop)
        sig.stop_underlying = float(stop)
        sig.target_underlying = float(sig.close + d * m["target_r"] * risk)
    return sig


_new_signal = G.new_signal


def new_signal(m, frame, regime, now):
    return side_signal(m, frame, regime, now) if m["family"] in SIDE_FAMILIES else _new_signal(m, frame, regime, now)


G.new_signal = new_signal


def side_member(family: str, gate: str = SIDEWAYS, **genes) -> dict:
    return {"kind": "NEW", "family": family, "gate": gate, "vwap_exit": "OFF", **genes}


def books() -> dict:
    out = {}
    for fam, genes in GRID.items():
        for values in itertools.product(*genes.values()):
            g = dict(zip(genes, values))
            name = f"{fam}|" + "|".join(f"{k}={v}" for k, v in g.items())
            out[name] = Y.book_of([side_member(fam, **g)])
    for i, b in enumerate(Y.null_fixed()):
        out[f"NULL{i:02d}|sideways"] = G.gated(b, SIDEWAYS)
    out["UNION_ADX"] = Y.book_of([Y.named(c, "adx_abs25:HIGH") for c in Y.NAMED])
    return out


RULE = {
    "question": "does any famous range-day entry make money, per lot, on the days the trend gate sits out?",
    "two_fold": "per family: the variant with the best H1 (Jan-May) per-lot net on sideways days is scored on H2 "
                "(Jun-Oct) and the H2 best on H1; a family helps only if both are > 0 and above the random books' "
                "median on the same half",
    "combo": "a family that helps is joined to UNION_ADX for the sideways days (at one lot); otherwise the advice "
             "stays: sit sideways days out",
    "status": "the ADX gate itself came from this year (O29g, in-sample); sideways entries are scored on it once",
}


def bindings() -> dict:
    out = G.bindings()
    for p in (HERE / "lab_i.py", HERE / "test_lab_i.py"):
        out["sources"][p.relative_to(ROOT).as_posix()] = Y.grid._sha(p)
    return out


def freeze() -> None:
    Y.write_new(HERE / "freeze.json", {"schema": "o29i_sideways_v1", "bindings": bindings(), "grid": GRID,
                                       "sideways_gate": SIDEWAYS, "books": books(), "rule": RULE,
                                       "qualification": "NOT_ASSESSED", "can_place_orders": False})
    print("frozen", len(books()), "books")


def _init() -> None:
    Y._worker_init()


def run(jobs: int) -> None:
    frozen = json.loads((HERE / "freeze.json").read_text())
    assert frozen["bindings"] == bindings(), "bound inputs changed since the freeze"
    rel = (HERE / "freeze.json").relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, "freeze not committed"
    Y.EVALS.mkdir(parents=True, exist_ok=True)
    O27F.deny_network()
    all_books = books()
    with ProcessPoolExecutor(max_workers=jobs, initializer=_init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(all_books.values()))
    Y.write_new(LOCAL / "results-raw.json", {"freeze_sha256": Y.grid._sha(HERE / "freeze.json"),
                                             "books": {n: Y.task_key(b, "year", Y.FULL) for n, b in all_books.items()},
                                             "trades": runner.trades})
    print("DONE", len(runner.trades), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["freeze", "run"])
    cli.add_argument("--jobs", type=int, default=5)
    args = cli.parse_args()
    freeze() if args.action == "freeze" else run(args.jobs)
