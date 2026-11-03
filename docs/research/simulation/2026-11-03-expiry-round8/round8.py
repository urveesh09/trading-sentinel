"""Round 8 (PLAN.md): X1 put/call asymmetry, X2 direction alignment, X3 delta strike, X4 the live 15:28 exit.

    python round8.py freeze    writes freeze.json once
    python round8.py score     refuses unless the freeze is committed and every hash matches -> results.json
"""
from __future__ import annotations
import hashlib, json, math, statistics as st, subprocess, sys
from dataclasses import asdict, replace
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
REPO = next(p for p in HERE.parents if (p / "python-engine").is_dir())
import r8_lab as R  # noqa: E402
sys.path.insert(0, str(SIM / "2026-11-03-expiry-auction"))
import auction as A  # noqa: E402  (Production snapshots and depth walks only)
L, X, E = R.L, R.X, R.E
FREEZE, OUT = HERE / "freeze.json", HERE / "results.json"
ARMS = {
    "E031": {}, "PUT2": dict(put_mult=2.), "PE_ONLY": dict(call_mult=0.),
    "ALIGN_WEEK": dict(align="WEEK"), "ALIGN_DAY": dict(align="DAY"),
    "ALIGN_WEEK2": dict(align="WEEK", align_mode="size"), "ALIGN_DAY2": dict(align="DAY", align_mode="size"),
    "DELTA15": dict(delta_target=.15), "DELTA25": dict(delta_target=.25), "DELTA35": dict(delta_target=.35),
}


# ---------------------------------------------------------------- X1a, the mechanism

def iv_at(t, i, j):
    s = float(t.close[i]); T = (930 - t.minute[i]) / X.YEAR_MIN; p = t.q[i, j, 3]
    if not (np.isfinite(p) and p > .5 and T > 0 and np.isfinite(s)):
        return None
    v = X.implied(float(p), s, float(t.strikes[j]), T, t.kinds[j] == 1)
    return v if np.isfinite(v) and v > 0 else None


def spot_vol(tapes):
    dr, dv, per_day = [], [], []
    for t in tapes:
        a, b = [], []
        for i in range(int(np.searchsorted(t.minute, 781)), int(np.searchsorted(t.minute, 900)) + 1):
            if not (np.isfinite(t.close[i]) and np.isfinite(t.close[i - 1])):
                continue
            k = min(set(t.strikes.tolist()), key=lambda k: abs(k - t.close[i]))
            ivs = []
            for kind in (1, -1):
                hit = np.flatnonzero((t.strikes == k) & (t.kinds == kind))
                if len(hit):
                    now, before = iv_at(t, i, hit[0]), iv_at(t, i - 1, hit[0])
                    if now and before:
                        ivs.append(now - before)
            if ivs:
                a.append(math.log(t.close[i] / t.close[i - 1])); b.append(st.mean(ivs))
        if len(a) > 20:
            per_day.append(float(np.polyfit(a, b, 1)[0])); dr += a; dv += b
    slope = float(np.polyfit(dr, dv, 1)[0])
    return dict(minutes=len(dr), slope_iv_per_unit_return=round(slope, 3), iv_points_per_0_1pct=round(slope * .001 * 100, 3),
                days=len(per_day), days_negative=sum(x < 0 for x in per_day))


def windows(tapes):
    rows = []
    for t in tapes:
        for w0 in range(780, 900, 10):
            i0, i1 = int(np.searchsorted(t.minute, w0)), int(np.searchsorted(t.minute, w0 + 10))
            if i1 >= t.n or not (np.isfinite(t.close[i0]) and np.isfinite(t.close[i1])):
                continue
            m = t.close[i1] / t.close[i0] - 1
            if abs(m) < .0015:
                continue
            d = 1 if m > 0 else -1; s = float(t.close[i0])
            js = [j for j in range(len(t.strikes)) if t.kinds[j] == d and 0 < d * (t.strikes[j] - s) <= 200
                  and np.isfinite(t.q[i0, j, 3]) and 5 <= t.q[i0, j, 3] <= 20 and np.isfinite(t.q[i1, j, 3])]
            if not js:
                continue
            j = min(js, key=lambda j: d * t.strikes[j])
            ask = E.up(float(t.q[i0, j, 3]) + E.half(float(t.q[i0, j, 3]))); bid = E.down(float(t.q[i1, j, 3]) - E.half(float(t.q[i1, j, 3])))
            rows.append(dict(side="PE" if d < 0 else "CE", move=abs(m), ret=bid / ask - 1))
    out = {}
    for label, sub in (("all", rows), ("moves_0.15_to_0.30pct", [r for r in rows if r["move"] <= .003])):
        for side in ("CE", "PE"):
            v = [r["ret"] for r in sub if r["side"] == side]
            out[f"{label}|{side}"] = dict(n=len(v), mean=round(st.mean(v), 4) if v else None, median=round(st.median(v), 4) if v else None,
                                          mean_move_pct=round(st.mean(r["move"] for r in sub if r["side"] == side) * 100, 3) if v else None)
    return out


# ---------------------------------------------------------------- X1b-X3, the books

def book(T, rule):
    out = {}
    for scope, tapes in (("2024", T[2024]), ("2025", T[2025]), ("both", T[2024] + T[2025])):
        for sc in ("ordinary", "adverse", "catastrophe"):
            r = R.run(tapes, rule, sc, details=(scope == "both" and sc == "ordinary"))
            s = r["summary"]
            out[f"{scope}|{sc}"] = {k: s[k] for k in ("net", "without_best", "worst", "drawdown", "trades", "profit_factor")}
            if scope == "both" and sc == "ordinary":
                ps = [p for d in r["days"] for p in d["positions"]]
                for side, sgn in (("CE", 1), ("PE", -1)):
                    v = [p["net"] for p in ps if p["direction"] == sgn]
                    out[f"side|{side}"] = dict(tickets=len(v), net=round(sum(v), 2), wins=sum(x > 0 for x in v),
                                               by_year={y: round(sum(p["net"] for p in ps if p["direction"] == sgn and p["day"][:4] == y), 2) for y in ("2024", "2025")})
    o = out["both|ordinary"]
    out["per_worst_day"] = round(o["net"] / -o["worst"], 3) if o["worst"] < 0 else None
    out["per_drawdown"] = round(o["net"] / o["drawdown"], 3) if o["drawdown"] else None
    return out


def beats(arm, base):
    return all(arm[f"{y}|{sc}"]["net"] > base[f"{y}|{sc}"]["net"] for y in ("2024", "2025") for sc in ("ordinary", "adverse"))


def efficient(arm, base):
    return bool(arm["per_worst_day"] and arm["per_drawdown"] and arm["per_worst_day"] >= base["per_worst_day"] and arm["per_drawdown"] >= base["per_drawdown"])


# ---------------------------------------------------------------- X4, the live 15:28 exit inside the auction

def auction_hold():
    days = {}
    for (u, d), snaps in sorted(A.production_days().items()):
        early = A.at(snaps, A.secs("15:14:50")); late = next((s for s in snaps if s["t"] >= A.secs("15:28:00")), None)
        if not early or not late:
            days[f"{u} {d}"] = dict(unavailable=True); continue
        lot = A.LOT[u]; frozen = early["spot"]; diffs = {"otm": [], "itm": []}; missing = 0
        for (k, o), leg in early["legs"].items():
            m = A.mid(leg)
            if m is None or m < 1 or leg["ts"] is None or early["t"] - leg["ts"] > A.FRESH_PROD:
                continue
            a = A.walk(leg["bids"], lot); lg = late["legs"].get((k, o))
            b = A.walk(lg["bids"], lot) if lg and lg["bids"] and lg["ts"] is not None and late["t"] - lg["ts"] <= A.FRESH_PROD else None
            if a is None or b is None:
                missing += 1; continue
            itm = (o == "CE" and k < frozen) or (o == "PE" and k > frozen)
            diffs["itm" if itm else "otm"].append((b - a) * lot)
        allv = diffs["otm"] + diffs["itm"]
        days[f"{u} {d}"] = dict(legs=len(allv), missing=missing, mean_all=round(st.mean(allv), 2) if allv else None,
                                mean_otm=round(st.mean(diffs["otm"]), 2) if diffs["otm"] else None,
                                mean_itm=round(st.mean(diffs["itm"]), 2) if diffs["itm"] else None, total=round(sum(allv), 2))
    ok = [v for v in days.values() if v.get("mean_all") is not None]
    return dict(days=days, negative_days=sum(v["mean_all"] < 0 for v in ok), measured_days=len(ok),
                total=round(sum(v["total"] for v in ok), 2), holding_loses=bool(sum(v["total"] for v in ok) < 0 and sum(v["mean_all"] < 0 for v in ok) >= 7))


# ---------------------------------------------------------------- freeze / score

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git(*x):
    return subprocess.run(["git", *x], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()


FILES = [HERE / "round8.py", HERE / "PLAN.md", HERE / "r8_lab.py", SIM / "2026-11-03-expiry-e031/lab.py",
         SIM / "2026-11-03-expiry-e03/e03_lab.py", SIM / "2026-11-03-expiry-e02/e02_lab.py", SIM / "2026-11-03-expiry-auction/auction.py", *A.PROD]


def freeze():
    assert not FREEZE.exists()
    FREEZE.write_text(json.dumps(dict(head=git("rev-parse", "HEAD"), written_before_scoring=True, arms=ARMS,
                                      files={str(p): sha(p) for p in FILES}), indent=2) + "\n", encoding="utf-8")
    print("FROZEN")


def score():
    fz = json.loads(FREEZE.read_text(encoding="utf-8"))
    for p, d in fz["files"].items():
        assert sha(p) == d, p
    rel = str(FREEZE.relative_to(REPO)).replace("\\", "/")
    assert git("log", "-1", "--format=%H", "--", rel) and not git("status", "--porcelain", "--", rel)
    T = L.tapes(); R.load_week([t.day for y in (2024, 2025) for t in T[y]])
    out = dict(freeze_head=fz["head"], x1a={}, books={}, verdict={})
    for y in (2024, 2025):
        out["x1a"][str(y)] = dict(spot_vol=spot_vol(T[y]), windows=windows(T[y]))
        print("X1a", y, json.dumps(out["x1a"][str(y)]), flush=True)
    a = out["x1a"]
    out["verdict"]["X1a_slope_negative_both"] = all(a[y]["spot_vol"]["slope_iv_per_unit_return"] < 0 for y in ("2024", "2025"))
    out["verdict"]["X1a_puts_beat_calls_both"] = all(a[y]["windows"]["all|PE"]["mean"] > a[y]["windows"]["all|CE"]["mean"] for y in ("2024", "2025"))
    for name, extra in ARMS.items():
        out["books"][name] = book(T, replace(R.E031, **extra))
        b = out["books"][name]
        print(name, {k: v["net"] for k, v in b.items() if "|" in k and k.split("|")[0] in ("2024", "2025", "both")},
              "side", b["side|CE"], b["side|PE"], "eff", b["per_worst_day"], b["per_drawdown"], flush=True)
    base = out["books"]["E031"]; bk = out["books"]
    out["verdict"]["PUT2"] = beats(bk["PUT2"], base) and efficient(bk["PUT2"], base)
    for n in ("ALIGN_WEEK", "ALIGN_DAY"):
        out["verdict"][n] = beats(bk[n], base)
    for n in ("ALIGN_WEEK2", "ALIGN_DAY2"):
        out["verdict"][n] = beats(bk[n], base) and efficient(bk[n], base)
    out["verdict"]["DELTA"] = sum(beats(bk[n], base) for n in ("DELTA15", "DELTA25", "DELTA35")) >= 2
    out["x4"] = auction_hold(); out["verdict"]["X4_holding_to_1528_loses"] = out["x4"]["holding_loses"]
    print("X4", json.dumps({k: v for k, v in out["x4"].items() if k != "days"}), json.dumps(out["x4"]["days"]), flush=True)
    print("VERDICT", json.dumps(out["verdict"]), flush=True)
    OUT.write_text(json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    {"freeze": freeze, "score": score}[sys.argv[1]]()
