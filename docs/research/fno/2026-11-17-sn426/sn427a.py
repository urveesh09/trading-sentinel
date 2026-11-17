"""SN427 A: Gold's expiry-morning candidates from a hooked N11 / R0.85 rerun (PLAN.md section 1, frozen at 123301ac;
details fixed here before any number). Research only; no frozen file is edited and no saved evaluation is overwritten.

    N08_YEAR=<2023|2024|2025|2026> python sn427a.py <year>

In memory only, every replay's funnel becomes a recording Counter: when the engine's SingleLegReplay._entry counts
`chain_unavailable:calendar_expiry_not_archived` (python-engine/fno_policy_replay.py: a signal that passed every N11 gate
before the chain, on a session whose calendar expiry is not archived = a NIFTY expiry day), the candidate's clock, signal
bar, direction, signal stop level, futures price and calendar expiry are appended. The N11 and R0.85 panel books are rerun
in process (n11_lab's patches, Y.EVALS pointed at _local/n11-rerun-<year>). Wiring check: each book's task key must equal
the saved keys-panel-<year>.json key, and the rerun's trade economics must equal the saved evaluation's.
Writes _local/sn427a-<year>.json: candidates (one per book, day, signal bar, direction) and the parity result.
"""
from __future__ import annotations

import collections
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
YEAR = sys.argv[1] if len(sys.argv) > 1 else ""
assert YEAR in ("2023", "2024", "2025", "2026") and os.environ.get("N08_YEAR") == YEAR, "set N08_YEAR to the same year"
N11 = HERE.parents[1] / "simulation" / "2026-11-02-fno-n11"
sys.path.insert(0, str(N11))
import n11_lab as N  # noqa: E402

Y = N.Y
replay = Y.replay
KEY = "chain_unavailable:calendar_expiry_not_archived"
OUTDIR = HERE / "_local"
CANDS: list = []


class Recording(collections.Counter):
    def __setitem__(self, key, value):
        if key == KEY and value > self.get(key, 0):
            loc = sys._getframe(1).f_locals
            sig, now, obs = loc.get("sig"), loc.get("now"), loc.get("obs")
            if sig is not None and now is not None:
                CANDS.append({"at": now.isoformat(), "day": now.date().isoformat(), "bar_ts": str(sig.bar_ts),
                              "direction": getattr(sig.direction, "value", str(sig.direction)),
                              "stop_underlying": getattr(sig, "stop_underlying", None), "atr": getattr(sig, "atr", None),
                              "future": None if obs is None else float(obs.future.ltp), "expiry": str(loc.get("expiry")),
                              "open_positions": len(loc["book"].open) if loc.get("book") is not None else None})
        super().__setitem__(key, value)


_init = replay.SingleLegReplay.__init__


def init(self, *a, **k):
    _init(self, *a, **k)
    self.funnel = Recording()


replay.SingleLegReplay.__init__ = init


def main():
    out = OUTDIR / f"sn427a-{YEAR}.json"
    if out.exists():
        raise SystemExit(f"{out.name} exists: run once")
    Y.EVALS = OUTDIR / f"n11-rerun-{YEAR}"
    Y.EVALS.mkdir(parents=True, exist_ok=True)
    books = N.panel_books()
    saved_keys = json.loads((N11 / "_local" / f"keys-panel-{YEAR}.json").read_text(encoding="utf-8"))
    window = N.B.C.WINDOW
    res = {"year": YEAR, "window": list(window), "books": {}, "candidates": []}
    for name in ("N11", "R0.85"):
        book = books[name]
        key = Y.task_key(book, "year", window)
        assert key == saved_keys[name], (name, key, saved_keys[name])
        CANDS.clear()
        _k, trades = Y.evaluate((book, "year", window))
        saved = json.loads((N11 / "_local" / "evals" / f"{key}.json").read_text(encoding="utf-8"))["trades"]
        same = N.T.economics(trades) == N.T.economics(saved)
        assert same, f"{name} {YEAR}: the rerun's trades differ from the saved evaluation"
        seen, kept = set(), []
        for c in CANDS:
            k2 = (c["day"], c["bar_ts"], c["direction"])
            if k2 in seen:
                continue
            seen.add(k2)
            kept.append({**c, "book": name})
        res["books"][name] = {"key": key, "trades": len(trades), "parity": same, "funnel_hits": len(CANDS), "candidates": len(kept),
                              "expiry_days": len({c["day"] for c in kept})}
        res["candidates"] += kept
        print(name, YEAR, json.dumps(res["books"][name]), flush=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
