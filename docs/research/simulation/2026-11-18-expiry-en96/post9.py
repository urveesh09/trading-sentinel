"""POST-SCORE DIAGNOSTICS (descriptive; not candidates, not re-scores; frozen verdicts in results9.json stand).

Written after reading results9.json, so every number here is selected-after-the-fact and carries no evidential weight
beyond explaining the frozen results. Any use needs a new registration on sessions never studied. Writes post9.json.

(a) Exit-target transfer. EN110's grid says informed EN87 parents earn more when the first profit target is +150% instead
    of +100%. Is that specific to OI-confirmed parents, or a property of E03 exits? Same change (target 1.5, everything
    else native) on E03_env, native E03.2 and native EN55.
(b) Explanatory receipts for three inert/degenerate families: EN98 extension at EN87 events (units of E03's 10-bar ATR),
    EN102 minimum d*S15 on the fixed entry basket during every EN87 hold, EN99 arm outcomes.
"""
from dataclasses import replace
from collections import Counter
from pathlib import Path
import json
import numpy as np
import round8  # noqa: F401
import data8, lab8, signals8
from data8 import basket
import families9 as F, signals9 as S9, lab9, score9 as S
L7 = lab8.L7
HERE = Path(__file__).resolve().parent


def summary(book, rule):
    o, tk, _, _ = S.run_indep(book, rule, scen=("ordinary", "adverse"))
    n = len(book); od = [o["ordinary"][k] for k in range(n)]; ad = [o["adverse"][k] for k in range(n)]
    wo = lab9.wallet9(book, rule, "ordinary"); wa = lab9.wallet9(book, rule, "adverse")
    return dict(ordinary=S.metrics(od, tk), adverse=S.metrics(ad), halves_ordinary=[round(sum(d["net"] for d in od[:100]), 2), round(sum(d["net"] for d in od[100:]), 2)],
                wallet={sc: {k: w[k] for k in ("P", "liq_dd", "halted", "first_halt")} for sc, w in (("ordinary", wo), ("adverse", wa))}), tk


def main():
    B, _ = data8.historical_books()
    for u, book in B.items():
        signals8.prepare(book); F.prepare9(book)
    out = dict(label="POST-SCORE DIAGNOSTIC: descriptive, selected after reading the results; no verdict or candidate", transfer={})
    for u in ("NIFTY", "SENSEX"):
        for name in ("E03_env", "E032_native", "EN55_native"):
            base = lab9.R9(lab8.ARMS[name])
            a, ta = summary(B[u], base); b, tb = summary(B[u], replace(base, target=1.5))
            out["transfer"][f"{name}|{u}"] = dict(native=a, target_150=b, tickets=S.compare(tb, ta))
            print(u, name, "native", a["ordinary"]["net"], a["adverse"]["net"], "target1.5", b["ordinary"]["net"], b["adverse"]["net"], flush=True)
    N = B["NIFTY"]; X = []; mins = []
    A = json.loads((HERE / "anatomy9.json").read_text())
    by = {t.day: t for t in N}
    for t in N:
        for i in np.flatnonzero(t.signals8["GATE"]):
            X.append(round(S9.extension(t, int(i), int(t.signals8["GATE"][i])), 3))
    for x in A["tickets"]["REF:EN87|NIFTY"]:
        t = by[x["day"]]; e = x["entry_i"]; end = x["exit_i"] or t.n - 1; pairs = basket(t, e)
        v = [x["d"] * S9.ref_score(t, i, 15, pairs) for i in range(e, end)]
        mins.append(round(min(v), 4))
    e03x = [S9.extension(t, int(i), int(t.e03[i])) for t in N for i in np.flatnonzero(t.e03)]
    out["EN98_extension_at_EN87_events_ATR10_units"] = dict(n=len(X), min=min(X), median=float(np.median(X)), max=max(X),
                                                            all_E03_env_events_share_at_or_below_2=round(float(np.mean(np.array(e03x) <= 2)), 3))
    out["EN102_min_signed_S15_fixed_basket_during_EN87_holds"] = dict(parents=len(mins), negative=sum(m < 0 for m in mins), values=sorted(mins))
    reg = {c.id: c for c in F.registry()}; arms = {}
    for cid in [c for c in reg if c.startswith(("EN99:confirm", "EN99:reclaim"))]:
        c = reg[cid]; r = c.rule()
        for t in N:
            F.build(t, c.spec, c.id, r)
        arms[cid] = dict(Counter(x["status"] for t in N for x in t.logs9.get(cid, [])))
    out["EN99_arm_outcomes"] = arms
    S.write(HERE / "post9.json", out); print("POST9 written", flush=True)


if __name__ == "__main__":
    main()
