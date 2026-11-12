"""SN06: the frozen rule once, then per-year wallet tables for benchmark / SN06 pick / combined (descriptive)."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-11-12-sn03")]
import sn06 as Z
import sn03 as B

def pick(E, fold, null):
    train = tuple(y for y in Z.YEARS if y != fold) if fold != "ALL" else Z.YEARS
    tag = f"ga:{fold}:{'null' if null else 'real'}:"
    c = [r for r in E.values() if r["genome"]["null"] == null and (r["origin"] == "pool" or r["origin"].startswith(tag))]
    return max(c, key=lambda r: Z.fitness(r, train))

def ledger(years, mode, g, cap):
    W, steps, prog = 15000.0, 0, 0.0
    per = {y: {"net": 0.0, "refilled": 0.0, "won": 0, "lost": 0, "none": 0, "wallet_end": 0} for y in Z.YEARS}
    for y in Z.YEARS:
        Y = years[y]; n11 = Y.sigs("N11")
        for S in Y.ordered():
            lots = max(1, int(W // 15000))
            if mode == "bench" or (mode == "combo" and S.day in n11):
                x = B.play_day(S, n11.get(S.day, []), {"lots": lots}, W, 0.2 * W)["net"]
            elif mode in ("sn06", "combo"):
                x = sum(Z.run_day(S, g, W, 0.2 * W)["net"] for _ in range(1)) if lots == 1 else \
                    lots * Z.run_day(S, g, W / lots, 0.2 * W / lots)["net"]
            else:
                x = 0.0
            p = per[y]; p["net"] += x; p["refilled"] += max(0.0, -x)
            p["won" if x > 0 else "lost" if x < 0 else "none"] += 1
            prog += x
            while prog >= W and steps < cap:
                prog -= W; W *= 1.5; steps += 1
            p["wallet_end"] = round(W)
    tot = {k: round(sum(per[y][k] for y in Z.YEARS)) for k in ("net", "refilled", "won", "lost", "none")}
    return {"per_year": {y: {k: round(v) for k, v in per[y].items()} for y in Z.YEARS}, "total": tot, "steps": steps}

if __name__ == "__main__":
    out = HERE / "results.json"
    if out.exists():
        raise SystemExit("scored once already")
    E = Z.load_evals()
    res = {"loyo": {}}
    for y in Z.YEARS:
        res["loyo"][y] = {k: {"genome": (p := pick(E, y, k == "null"))["genome"], "heldout": p["years"][y]} for k in ("real", "null")}
    real = [res["loyo"][y]["real"]["heldout"]["net"] for y in Z.YEARS]
    null = [res["loyo"][y]["null"]["heldout"]["net"] for y in Z.YEARS]
    fin = pick(E, "ALL", False)
    chk = {"heldout_positive": sum(x > 0 for x in real), "heldout_sum": round(sum(real)), "null_sum": round(sum(null)),
           "final_years_positive": sum(fin["years"][y]["net"] > 0 for y in Z.YEARS)}
    chk["verdict"] = "PROMISING (paper/forward only)" if (chk["heldout_positive"] >= 3 and chk["heldout_sum"] > 0 and
        chk["heldout_sum"] > chk["null_sum"] and chk["final_years_positive"] == 4) else "NOT PROVEN"
    res["checks"], res["final"] = chk, {"genome": fin["genome"], "years": fin["years"]}
    print(json.dumps(chk, indent=1))
    for y in Z.YEARS:
        print(y, {k: (res["loyo"][y][k]["heldout"]["net"], res["loyo"][y][k]["heldout"]["active"]) for k in ("real", "null")})
    print("final", {y: (fin["years"][y]["net"], fin["years"][y]["active"]) for y in Z.YEARS}, fin["genome"])
    years = {y: B.Year(y) for y in Z.YEARS}
    for y in Z.YEARS:
        for S in years[y].ordered():
            pass
    res["tables"] = {}
    for mode in ("bench", "sn06", "combo"):
        for cap in range(0, 6):
            r = ledger(years, mode, fin["genome"], cap)
            res["tables"][f"{mode}|{cap}"] = r
            print(mode, cap, r["total"], r["steps"], {y: (r["per_year"][y]["net"], r["per_year"][y]["refilled"]) for y in Z.YEARS}, flush=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
