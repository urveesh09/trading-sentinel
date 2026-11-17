"""SN432: 5 and 30 seconds of fill persistence on the development recorder slice (PLAN.md section 1, frozen at 123301ac;
details fixed here before any number). Nov 16's recorder copy is plumbing data (before the forward start); one morning
is plumbing evidence only, and the prospective test is specified in the README.

Decisions: every whole minute 09:16:00 - 10:18:00 (t = 60, 120, ... 3780 s after 09:15) for four contracts on the front
weekly: ATM CE / PE and 1-ITM CE / PE (ATM from the index's last price at t). ask_t = the inside ask of the last fresh
valid packet at or before t; cap = ask_t + 2 ticks.
  IMMEDIATE   fw2.entry at t with the cap (the first fresh packet 0.5 - 2.5 s after t holding one lot; walked)
  CONFIRM-w   (w = 5, 30 s) only if every valid packet in (t, t + w] kept the inside ask <= ask_t and five-level depth
              >= one lot, then fw2.entry at t + w with the same cap; else WAITED_OUT
  RANDOM      fw2.entry at t + u (u seeded uniform 0 - 30 s) with the same cap (the time-matched control)
Outcome per filled decision: the walked one-lot bid of the first fresh packet >= t + 60 s and >= t + 300 s (fw2.exit_at),
net per lot = (bid - fill) x lot, before charges and stress. A decision IMMEDIATE fills but another arm does not is
charged IMMEDIATE's outcome as the missed result. Also: how long the inside ask stays <= ask_t after t (seconds).
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn351"))
sys.path.insert(0, str(FNO / "2026-11-16-sn301"))
import fw2  # noqa: E402
import fw5  # noqa: E402

OUT = HERE / "results-sn432.json"
FOLDER = Path(r"C:\Users\Urveesh\AppData\Local\Temp\claude\f191b6166a36c84a\b7c0aa9b-c954-4f08-9df8-57422081ea0c\scratchpad\rec\2026-11-16")
TICK = 0.05


def last_fresh(d, t):
    k = int(np.searchsorted(d["t"], t, side="right")) - 1
    while k >= 0 and not d["ok"][k]:
        k -= 1
    return k if k >= 0 and t - d["t"][k] <= 2.0 else None


def held(d, t, w, ask_t, lot):
    m = (d["t"] > t) & (d["t"] <= t + w) & d["ok"]
    if not m.any():
        return False
    return bool(np.all(d["ask"][m] <= ask_t + 1e-9) and np.all(d["a5"][m] >= lot))


def persist(d, t, ask_t):
    m = (d["t"] > t) & d["ok"] & (d["ask"] > ask_t + 1e-9)
    idx = np.flatnonzero(m)
    return float(d["t"][idx[0]] - t) if len(idx) else None


def outcome(day, tok, k, px, t):
    out = {}
    for h in (60, 300):
        b, _tx, st = fw2.exit_at(day, tok, t + h)
        out[f"net{h}"] = None if b is None else round((b - px) * day.lot, 2)
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN432 is run once")
    day = fw2.Day(FOLDER, fw5.load_open(FOLDER))
    rows = []
    for t in range(60, 3781, 60):
        atm = day.atm(float(t))
        if atm is None:
            continue
        for side in ("CE", "PE"):
            for dep in (0, 1):
                k = atm + (-dep * 50 if side == "CE" else dep * 50)
                tok = day.opt.get((day.front, k, side))
                d = None if tok is None else day.D.get(tok)
                if d is None or "ask" not in d:
                    continue
                j = last_fresh(d, float(t))
                if j is None:
                    continue
                ask_t = float(d["ask"][j])
                cap = ask_t + 2 * TICK
                r = {"t": t, "side": side, "depth": dep, "ask_t": ask_t, "ask_persist_s": persist(d, float(t), ask_t)}
                g, why = fw2.entry(day, tok, float(t), cap=cap)
                r["IMMEDIATE"] = {"state": "FILLED", "px": g[1], **outcome(day, tok, g[0], g[1], float(t))} if g else {"state": "MISSED", "why": why}
                for w in (5, 30):
                    if held(d, float(t), w, ask_t, day.lot):
                        g2, why2 = fw2.entry(day, tok, float(t + w), cap=cap)
                        r[f"CONFIRM-{w}"] = {"state": "FILLED", "px": g2[1], **outcome(day, tok, g2[0], g2[1], float(t))} if g2 else {"state": "MISSED", "why": why2}
                    else:
                        r[f"CONFIRM-{w}"] = {"state": "WAITED_OUT"}
                u = random.Random(f"sn432-{t}-{side}-{dep}").uniform(0, 30)
                g3, why3 = fw2.entry(day, tok, float(t) + u, cap=cap)
                r["RANDOM"] = {"state": "FILLED", "px": g3[1], **outcome(day, tok, g3[0], g3[1], float(t))} if g3 else {"state": "MISSED", "why": why3}
                rows.append(r)
    res = {"day": day.day, "decisions": len(rows)}
    for arm in ("IMMEDIATE", "CONFIRM-5", "CONFIRM-30", "RANDOM"):
        f = [r for r in rows if r[arm]["state"] == "FILLED"]
        blk = {"filled": len(f), "states": {s: sum(1 for r in rows if r[arm]["state"] == s) for s in ("FILLED", "MISSED", "WAITED_OUT")}}
        for h in (60, 300):
            xs = [r[arm][f"net{h}"] for r in f if r[arm].get(f"net{h}") is not None]
            blk[f"mean_net{h}_per_lot"] = round(float(np.mean(xs)), 1) if xs else None
            charged = []
            for r in rows:
                if r[arm]["state"] == "FILLED" and r[arm].get(f"net{h}") is not None:
                    charged.append(r[arm][f"net{h}"])
                elif r["IMMEDIATE"]["state"] == "FILLED" and r["IMMEDIATE"].get(f"net{h}") is not None and arm != "IMMEDIATE":
                    charged.append(0.0)
            blk[f"per_decision_net{h}"] = round(float(np.mean(charged)), 1) if charged else None
            missed_w = [r["IMMEDIATE"][f"net{h}"] for r in rows if r[arm]["state"] != "FILLED" and r["IMMEDIATE"]["state"] == "FILLED" and r["IMMEDIATE"].get(f"net{h}") is not None]
            blk[f"missed_immediate_winners{h}"] = sum(1 for x in missed_w if x > 0)
            blk[f"missed_immediate_net{h}"] = round(sum(missed_w), 1)
        if arm != "IMMEDIATE":
            both = [r for r in rows if r[arm]["state"] == "FILLED" and r["IMMEDIATE"]["state"] == "FILLED"]
            blk["paired_fill_diff_per_lot"] = round(float(np.mean([(r["IMMEDIATE"]["px"] - r[arm]["px"]) * day.lot for r in both])), 2) if both else None
        res[arm] = blk
    ps = [r["ask_persist_s"] for r in rows if r["ask_persist_s"] is not None]
    res["ask_persist_seconds"] = {"median": round(float(np.median(ps)), 2) if ps else None, "p25": round(float(np.percentile(ps, 25)), 2) if ps else None,
                                  "p75": round(float(np.percentile(ps, 75)), 2) if ps else None, "never_rose": sum(1 for r in rows if r["ask_persist_s"] is None)}
    res["rows"] = rows
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, default=float))


if __name__ == "__main__":
    main()
