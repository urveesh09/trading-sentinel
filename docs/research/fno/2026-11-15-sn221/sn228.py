"""SN228 - THE EXAM, once (PLAN.md): NIFTY weekly expiries Oct 1 2020 - Nov 25 2021, never read by any study.
Frozen by SN227 (results-sn227.json, committed before this runs):
  PICK      = STRADDLE kM settle H15x2 (the filtered PICK failed the random-skip null, so its unfiltered base replaced it);
  RUNNER 1  = STRADDLE kM settle stop1 H15x2, RUNNER 2 = STRADDLE kM gate H15x2 (replaced the same way);
  PLATEAU   = the per-week average of SN227's 20 eligible variants;
  references: WK-S, WK-G, the k1 ATM straddle (P4), the best hedged WK-S (STRANGLE 0.5 k3 settle stop1 H15x2),
              breach 0.5 + gate (SN218, minute engine).
Information only (declared before the exam): the two filtered originals (ADX<25) and the unhedged STRADDLE kM settle.
Pass (PICK): P1 EXAM net > 0; P2 EXAM worst month >= -34,163 (per option lot). Reported: P3 five-sample total, P4 PICK
beats the k1 straddle on EXAM."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import grid  # noqa: E402
import sn227  # noqa: E402
import wk3  # noqa: E402

wk, wk2 = wk3.wk, wk3.wk2
E3 = -34163


def tup(v):
    return (v[0], v[1] if v[1] in ("F", "M") else int(v[1]), v[2], v[3], v[4])


def run(E, v):
    tr = wk3.book3(E, *tup(v))
    L = grid.lots_of(tup(v))
    return tr, wk3.summary(tr, E.W, L), L


if __name__ == "__main__":
    out_path = HERE / "results-sn228.json"
    if out_path.exists():
        raise SystemExit("SN228 is scored once")
    frozen = json.loads((HERE / "results-sn227.json").read_text(encoding="utf-8"))
    wk3.UNSEAL_EXAM = True
    E = wk3.sample("EXAM")
    res = {"exam_weeks": E.W, "first_expiry": E.weeks[0][0], "last_expiry": E.weeks[-1][0], "candidates": {}}
    cands = {}
    for k, it in frozen["picks"].items():
        b = it.get("replaced_by_unfiltered_base")
        cands[k] = b["variant"] if b else it["variant"]
        if b:
            cands[f"{k} original (filtered, information)"] = it["variant"]
    for k, it in frozen["references"].items():
        if "variant" in it:
            cands[f"ref {k}"] = it["variant"]
    cands["info: unhedged STRADDLE kM settle"] = ["STRADDLE", "M", "settle", "none", "none"]
    ledgers = {}
    for lab, v in cands.items():
        tr, s, L = run(E, v)
        res["candidates"][lab] = {"variant": wk3.vname(tup(v)), "exam": s}
        ledgers[lab] = {t["expiry"]: t["net"] / L for t in tr}
        print(f"SN228 {lab:44s} {wk3.vname(tup(v)):36s} net {s['net']:>9} trades {s['trades']:>3} win {s['win_pct']:>5} worst {s['worst']:>8} "
              f"month {s['worst_month']:>8} months+ {s['months_positive']} by_year {s['by_year']} orders {s['orders']} costs {s['hedge_costs']}", flush=True)
    tr = wk2.book2(wk.NIFTY, E.data, E.mins, E.weeks, wk2.WK_S, {"breach": 0.5, "gate": -0.25})
    rr = [{"entry": t["entry"], "expiry": t["expiry"], "exit_day": t["exit_day"], "net": t["net"]} for t in tr]
    s = wk3.summary(rr, E.W)
    res["candidates"]["ref breach 0.5 + gate"] = {"variant": "WK-S + breach 0.5 + gate -0.25 (wk2)", "exam": s}
    print(f"SN228 {'ref breach 0.5 + gate':44s} net {s['net']:>9} trades {s['trades']} worst {s['worst']} month {s['worst_month']} by_year {s['by_year']}", flush=True)
    T = grid.table()
    elig = [v for v in T if not sn227.eligible(v, T[v])]
    pl = {}
    for v in elig:
        trv = wk3.book3(E, *v)
        L = grid.lots_of(v)
        for t in trv:
            pl.setdefault(t["expiry"], []).append(t["net"] / L)
    weeks = [e for e, _d in E.weeks]
    pnet = {e: sum(pl.get(e, [])) / len(elig) for e in weeks}
    mo = {}
    for e in weeks:
        mo[e[:7]] = mo.get(e[:7], 0.0) + pnet[e]
    res["candidates"]["PLATEAU"] = {"members": len(elig), "exam": {"net": round(sum(pnet.values())), "worst_week": round(min(pnet.values())),
                                                                    "worst_month": round(min(mo.values())),
                                                                    "months_positive": f"{sum(x > 0 for x in mo.values())} of {len(mo)}"}}
    print("SN228 PLATEAU", json.dumps(res["candidates"]["PLATEAU"]), flush=True)
    pk = res["candidates"]["PICK"]["exam"]
    seen = frozen["picks"]["PICK"]["replaced_by_unfiltered_base"]["rows"]
    res["pass"] = {"P1_exam_net_positive": pk["net"] > 0, "P2_worst_month_ok": pk["worst_month"] >= E3,
                   "P3_five_sample_total": sum(seen[n]["net"] for n in wk3.SEEN) + pk["net"],
                   "P4_beats_k1_straddle": pk["net"] > res["candidates"]["ref k1 ATM straddle"]["exam"]["net"]}
    res["pass"]["forward_paper_candidate"] = res["pass"]["P1_exam_net_positive"] and res["pass"]["P2_worst_month_ok"]
    res["pick_ledger_per_lot"] = {e: round(x) for e, x in sorted(ledgers["PICK"].items())}
    print("SN228 PASS", json.dumps(res["pass"]), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
