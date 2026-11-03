"""SELLER_PLAN.md: a defined-risk iron butterfly on expiry afternoons. Research only; read-only sources.

    python seller.py freeze    writes freeze-seller.json once
    python seller.py score     refuses unless the freeze is committed and every hash matches -> seller-results.json
"""
from __future__ import annotations
import hashlib, json, math, statistics as st, subprocess, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
REPO = next(p for p in HERE.parents if (p / "python-engine").is_dir())
sys.path.insert(0, str(SIM / "2026-11-03-expiry-e031"))
import lab as LAB  # noqa: E402  (the E02/E03 tapes, spread model and NFO fee helpers)
import auction as A  # noqa: E402  (Production snapshots, depth walk, native fees)
E, EP = LAB.E, A.EP
ARMS = [dict(T=T, steps=w, stop=s) for T in (780, 840) for w in (2, 4) for s in (None, .5, 1.)]
FREEZE, OUT = HERE / "freeze-seller.json", HERE / "seller-results.json"
STEP = {"NIFTY": 50, "SENSEX": 100}


def name(a):
    return f"T{a['T'] // 60}{a['T'] % 60:02d}_W{a['steps']}_S{a['stop'] or 'hold'}"


# ---------------------------------------------------------------- minute chains (2024 / 2025)

def px(t, i, j, side, scenario):
    """Execution price of one leg on bar i (the bar after the decision). side: 'buy' or 'sell'."""
    r = t.q[i, j]
    if not np.isfinite(r[:4]).all():
        return None
    raw = float(r[1] if side == "buy" else r[2]) if scenario == "catastrophe" else float(r[0])
    slip = E.half(raw) * (1 if scenario == "ordinary" else 2)
    if scenario == "adverse":
        slip += max(.05, raw * .01)
    return E.up(raw + slip) if side == "buy" else max(.05, E.down(raw - slip))


def mark(t, i, j, side):
    """Decision-time close +- half spread (what closing would cost, read on a completed bar)."""
    c = t.q[i, j, 3]
    if not np.isfinite(c):
        return None
    return c + E.half(float(c)) if side == "buy" else max(0., c - E.half(float(c)))


def leg_index(t, strike, kind):
    hit = np.flatnonzero((t.strikes == strike) & (t.kinds == kind))
    return int(hit[0]) if len(hit) else None


def chain_day(t, a, scenario):
    i = int(np.searchsorted(t.minute, a["T"]))
    if i + 1 >= t.n or not np.isfinite(t.close[i]):
        return dict(day=t.day, net=0., traded=False, why="no index")
    s = float(t.close[i]); k = round(s / 50) * 50; w = a["steps"] * 50
    legs = [(k, 1, "sell"), (k, -1, "sell"), (k + w, 1, "buy"), (k - w, -1, "buy")]
    idx = [leg_index(t, strike, kind) for strike, kind, _ in legs]
    if None in idx or not all(np.isfinite(t.q[i, j, 3]) for j in idx):
        return dict(day=t.day, net=0., traded=False, why="leg missing")
    fills = [px(t, i + 1, j, side, scenario) for j, (_, _, side) in zip(idx, legs)]
    if None in fills:
        return dict(day=t.day, net=0., traded=False, why="no entry fill")
    lot = 65
    credit = fills[0] + fills[1] - fills[2] - fills[3]
    if credit <= 0:
        return dict(day=t.day, net=0., traded=False, why="no credit")
    fees = sum(E.fee(p, lot, side == "buy") for p, (_, _, side) in zip(fills, legs))
    exit_i, reason = None, "HELD"
    flat = int(np.searchsorted(t.minute, 928))
    for b in range(i + 1, min(flat, t.n - 1)):
        if a["stop"] is None:
            break
        m = [mark(t, b, j, "buy" if side == "sell" else "sell") for j, (_, _, side) in zip(idx, legs)]
        if None in m:
            continue
        cost = m[0] + m[1] - m[2] - m[3]
        if cost >= credit * (1 + a["stop"]):
            exit_i, reason = b + 1, "STOP"; break
    exit_i = exit_i or min(flat + 1, t.n - 1)
    closes, missing = [], 0
    for j, (strike, kind, side) in zip(idx, legs):
        p = px(t, exit_i, j, "buy" if side == "sell" else "sell", scenario)
        if p is None:
            spot = float(t.close[exit_i - 1]) if np.isfinite(t.close[exit_i - 1]) else s
            p = max(0., (spot - strike) if kind == 1 else (strike - spot)); missing += 1
        closes.append(p)
    fees += sum(E.fee(p, lot, side == "sell") for p, (_, _, side) in zip(closes, legs) if p > 0)
    gross = ((fills[0] - closes[0]) + (fills[1] - closes[1]) + (closes[2] - fills[2]) + (closes[3] - fills[3])) * lot
    return dict(day=t.day, net=round(gross - fees, 2), traded=True, reason=reason, credit=round(credit, 2), k=k,
                max_loss=round((w - credit) * lot + fees, 2), missing=missing, move=round(float(t.close[exit_i - 1]) - s, 2))


def summarize(rows):
    v = [r["net"] for r in rows if r["traded"]]
    if not v:
        return dict(traded=0)
    gains = sum(x for x in v if x > 0); loss = -sum(x for x in v if x < 0)
    return dict(traded=len(v), net=round(sum(v), 2), without_best=round(sum(v) - max(v), 2), worst=round(min(v), 2), best=round(max(v), 2),
                wins=sum(x > 0 for x in v), profit_factor=round(gains / loss, 3) if loss else None,
                mean=round(st.mean(v), 2), max_loss_mean=round(st.mean(r["max_loss"] for r in rows if r["traded"]), 2),
                stops=sum(r.get("reason") == "STOP" for r in rows if r["traded"]), missing_legs=sum(r.get("missing", 0) for r in rows if r["traded"]))


# ---------------------------------------------------------------- Production snapshots (closing-auction era)

def snap_walk(leg, side, lot):
    levels = leg["asks"] if side == "buy" else leg["bids"]
    return A.walk(levels, lot) if levels else None


def prod_day(u, day, snaps, a, settle):
    lot, step = A.LOT[u], STEP[u]; fees_s = EP.fee_schedule("NFO" if u == "NIFTY" else "BFO")
    n = next((x for x, s in enumerate(snaps) if s["t"] >= a["T"] * 60), None)
    if n is None or n + 1 >= len(snaps) or snaps[n]["spot"] is None:
        return dict(day=day, traded=False, why="no decision snapshot", net=0.)
    s = snaps[n]["spot"]; k = round(s / step) * step; w = a["steps"] * step
    legs = [(k, "CE", "sell"), (k, "PE", "sell"), (k + w, "CE", "buy"), (k - w, "PE", "buy")]
    nxt = snaps[n + 1]
    fills = []
    for strike, opt, side in legs:
        leg = nxt["legs"].get((strike, opt))
        fresh = leg and leg["ts"] is not None and nxt["t"] - leg["ts"] <= A.FRESH_PROD
        fills.append(snap_walk(leg, side, lot) if fresh else None)
    if None in fills:
        return dict(day=day, traded=False, why="leg not fillable", net=0.)
    credit = fills[0] + fills[1] - fills[2] - fills[3]
    fees = sum(EP.sell_charges(p, lot, fees_s) if side == "sell" else EP.buy_charges(p, lot, fees_s) for p, (_, _, side) in zip(fills, legs))
    reason, closes = "HELD", None
    for snap in snaps[n + 2:]:
        if a["stop"] is not None and snap["t"] < A.secs("15:30:00"):
            m = []
            for strike, opt, side in legs:
                leg = snap["legs"].get((strike, opt))
                q = (leg["asks"] if side == "sell" else leg["bids"]) if leg else None
                m.append(q[0][0] if q else None)
            if None not in m and m[0] + m[1] - m[2] - m[3] >= credit * (1 + a["stop"]):
                c = [snap_walk(snap["legs"][(strike, opt)], "buy" if side == "sell" else "sell", lot) for strike, opt, side in legs]
                if None not in c:
                    closes, reason = c, "STOP"; break
        if snap["t"] >= A.secs("15:31:00"):
            c = []
            for strike, opt, side in legs:
                leg = snap["legs"].get((strike, opt))
                c.append(snap_walk(leg, "buy" if side == "sell" else "sell", lot) if leg else None)
            closes = c; break
    settled = 0
    closes = closes or [None] * 4
    for x, (strike, opt, side) in enumerate(legs):
        if closes[x] is None:
            intrinsic = max(0., settle - strike) if opt == "CE" else max(0., strike - settle)
            closes[x] = intrinsic * (1 - EP.EXERCISE_STT_PCT) if side == "buy" else intrinsic; settled += 1
        elif closes[x] > 0:
            fees += EP.buy_charges(closes[x], lot, fees_s) if side == "sell" else EP.sell_charges(closes[x], lot, fees_s)
    gross = ((fills[0] - closes[0]) + (fills[1] - closes[1]) + (closes[2] - fills[2]) + (closes[3] - fills[3])) * lot
    return dict(day=day, traded=True, reason=reason, credit=round(credit, 2), k=k, net=round(gross - fees, 2), settled_legs=settled,
                max_loss=round((w - credit) * lot + fees, 2), move=round(settle - s, 2))


# ---------------------------------------------------------------- freeze / score

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git(*x):
    return subprocess.run(["git", *x], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()


FILES = [HERE / "seller.py", HERE / "SELLER_PLAN.md", HERE / "auction.py", SIM / "2026-11-03-expiry-e031/lab.py",
         SIM / "2026-11-03-expiry-e03/e03_lab.py", SIM / "2026-11-03-expiry-e02/e02_lab.py", *A.PROD]


def freeze():
    assert not FREEZE.exists()
    FREEZE.write_text(json.dumps(dict(head=git("rev-parse", "HEAD"), written_before_scoring=True, arms=[name(a) for a in ARMS],
                                      files={str(p): sha(p) for p in FILES}), indent=2) + "\n", encoding="utf-8")
    print("FROZEN")


def score():
    fz = json.loads(FREEZE.read_text(encoding="utf-8"))
    for p, d in fz["files"].items():
        assert sha(p) == d, p
    rel = str(FREEZE.relative_to(REPO)).replace("\\", "/")
    assert git("log", "-1", "--format=%H", "--", rel) and not git("status", "--porcelain", "--", rel)
    T = LAB.tapes(); out = dict(freeze_head=fz["head"], chains={}, verdict={}, production={})
    for a in ARMS:
        nm = name(a); res = {}
        for y in (2024, 2025):
            for sc in ("ordinary", "adverse", "catastrophe"):
                rows = [chain_day(t, a, sc) for t in T[y]]
                res[f"{y}|{sc}"] = summarize(rows)
                if sc == "ordinary":
                    res[f"{y}|days"] = [dict(day=r["day"], net=r["net"], move=r.get("move"), credit=r.get("credit"), reason=r.get("reason")) for r in rows if r["traded"]]
        out["chains"][nm] = res
        ok = all(res[f"{y}|{sc}"].get("net", 0) > 0 for y in (2024, 2025) for sc in ("ordinary", "adverse")) \
            and all(res[f"{y}|ordinary"].get("without_best", 0) > 0 for y in (2024, 2025)) \
            and all(res[f"{y}|{sc}"].get("worst", 0) > -10000 for y in (2024, 2025) for sc in ("ordinary", "adverse"))
        out["verdict"][nm] = ok
        print(nm, "PASS" if ok else "fail", {k: (v.get("net"), v.get("without_best"), v.get("worst"), v.get("wins"), v.get("traded"))
                                            for k, v in res.items() if not k.endswith("days")}, flush=True)
    prod = A.production_days()
    settles = {k: next((s["spot"] for s in snaps if s["t"] >= A.secs("15:31:00") and s["spot"]), None) for k, snaps in prod.items()}
    for a in ARMS:
        nm = name(a)
        rows = [prod_day(u, d, snaps, a, settles[(u, d)]) for (u, d), snaps in sorted(prod.items()) if settles[(u, d)]]
        out["production"][nm] = dict(summary=summarize(rows), days=rows)
        print("production", nm, summarize(rows), flush=True)
    OUT.write_text(json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    {"freeze": freeze, "score": score}[sys.argv[1]]()
