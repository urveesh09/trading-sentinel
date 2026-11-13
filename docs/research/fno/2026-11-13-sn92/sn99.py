"""SN99 (+ SN97 part 1) - Gold's capital allocation: where the extra lots go (PLAN.md). Only sizing changes, so the
1-lot wallets A and B are unchanged by construction; C, the growth wallets and the deployed Rs 30k start move.
Variants (all on top of v5): futures relative volume (SN97, 9), per-setup full lots (15 subsets), drop one setup (4),
option cheapness at entry (4), India VIX (2), C equal-capital deep ITM (1). LOYO picks per wallet against v5; the
Gold pass rule of PLAN.md; robustness (+Rs 400, 1 minute late) for the LOYO picks; every wallet for the picks."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402

V5 = C.V5
SEL = ("C 30k sized", "G3 (Gold)", "G5")


def variants():
    vs = {"SN Gold v5": dict(V5)}
    for rule, x in itertools.product(("rv", "rv_and_vol", "rv_or_vol"), (1.2, 1.5, 2.0)):
        vs[f"SN97 {rule} x{x}"] = {**V5, "size": rule, "rv_x": x}
    for n in range(1, 5):
        for sub in itertools.combinations(C.EXPERTS, n):
            if n == 4:
                continue        # all four = v5 itself
            vs[f"SN99 full for {'+'.join(sub)}"] = {**V5, "size": "setup", "full_for": set(sub)}
    for e in C.EXPERTS:
        vs[f"SN99 drop {e}"] = {**V5, "drop": {e}}
    for r in ("cheap_hi", "cheap_lo", "cheap_hi&vol", "cheap_lo&vol"):
        vs[f"SN99 {r}"] = {**V5, "size": r, "cheap_med": None}
    for r in ("vix_hi&vol", "vix_lo&vol"):
        vs[f"SN99 {r}"] = {**V5, "size": r}
    vs["SN99 one deep ITM lot every day"] = {**V5, "size": "single"}
    return vs


def cheap_median():
    """The median R_today over every N11 / R0.85 entry minute of 2023 (a fixed level, taken before scoring 2024-26;
    2023 itself is then scored with an in-sample level, which favours nothing in particular)."""
    Ys = C.years()
    xs = []
    Y = Ys["2023"]
    for S in Y.ordered():
        for sg in C.L.sig_of(Y, S.day, V5):
            r = C.r_today(S, sg["i"])
            if r is not None:
                xs.append(r)
    return float(np.median(xs))


def gold_pass(res, Lw):
    v5 = res["SN Gold v5"]
    out = {}
    for w in ("C 30k sized", "G3 (Gold)"):
        L_ = Lw[w]
        held = [L_[y]["net"] for y in C.YEARS]
        base = [v5[w][y]["net"] for y in C.YEARS]
        out[w] = {"held_out": held, "v5": base, "sum": sum(held), "v5_sum": sum(base),
                  "years_at_least_v5": sum(h >= b for h, b in zip(held, base)),
                  "worst": min(res[L_[y]["pick"]][w][y]["worst"] for y in C.YEARS),
                  "v5_worst": min(v5[w][y]["worst"] for y in C.YEARS)}
    ok = all(o["sum"] > o["v5_sum"] and o["years_at_least_v5"] >= 3 and o["worst"] >= 1.1 * o["v5_worst"] for o in out.values())
    return out, ok


if __name__ == "__main__":
    out_path = HERE / "results-sn99.json"
    if out_path.exists():
        raise SystemExit("SN99 is scored once")
    C.years()
    med = cheap_median()
    vs = variants()
    for k, v in vs.items():
        if "cheap_med" in v:
            v["cheap_med"] = med
    res = {k: C.run(v) for k, v in vs.items()}
    tot = C.totals(res["SN Gold v5"])
    assert all(tot[k] == x for k, x in C.V5_TOTALS.items()), tot
    for k, r in sorted(res.items(), key=lambda kv: -C.totals(kv[1])["G3 (Gold)"]):
        t = C.totals(r)
        print(f"{k:34s} " + " ".join(f"{w.split()[0]} {t[w]:>8}" for w in ("A 15k 1 lot", "C 30k sized", "G3 (Gold)", "G5")), flush=True)
    Lw = {w: C.loyo_wallet(res, w) for w in SEL}
    for w, L_ in Lw.items():
        print(f"  held out {w:12s} sum {L_['sum']['net']:>8} (v5 {C.totals(res['SN Gold v5'])[w]})  picks",
              [(L_[y]['pick'], L_[y]['net']) for y in C.YEARS], flush=True)
    detail, ok = gold_pass(res, Lw)
    print("GOLD PASS RULE", detail, "PASS" if ok else "NOT PROVEN", flush=True)
    rob = {}
    for label, extra in (("stress 400", None), ("1 minute late", {"late": 1})):
        for w in ("C 30k sized", "G3 (Gold)"):
            s_pick = s_v5 = 0
            for y in C.YEARS:
                old = C.L.STRESS
                if extra is None:
                    C.L.STRESS = 400.0
                try:
                    vp = {**vs[Lw[w][y]["pick"]], **(extra or {})}
                    s_pick += C.run(vp)[w][y]["net"]
                    s_v5 += C.run({**V5, **(extra or {})})[w][y]["net"]
                finally:
                    C.L.STRESS = old
            rob[f"{label} | {w}"] = {"held_out_picks": s_pick, "v5": s_v5}
    print("ROBUSTNESS", rob, flush=True)
    big = {}
    for k in sorted({Lw[w][y]["pick"] for w in SEL for y in C.YEARS} | {"SN Gold v5"}):
        big[k] = C.panel(C.run(vs[k], C.BIG_WALLETS))
        print(f"--- {k}")
        for w, p in big[k].items():
            print(f"   {w:18s} net {p['net']:>9} by year {p['by_year']} refilled {p['refilled']:>8} w/l/none {p['w/l/none']} worst {p['worst']}")
    out_path.write_text(json.dumps({"cheap_median_2023": med, "totals": {k: C.totals(r) for k, r in res.items()},
                                    "variants": C.jsonable(res), "loyo": Lw, "pass_detail": detail, "PASS": ok,
                                    "robust": rob, "every_wallet": big}, indent=1, default=str), encoding="utf-8")
