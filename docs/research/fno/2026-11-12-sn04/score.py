"""SN04 scoring: the frozen rule once, then the per-strategy wallet tables (descriptive)."""
import json, sys
from pathlib import Path
import sn04 as Z

def pick(evals, fold, null):
    train = Z.folds()[fold]
    tag = f"ga:{fold}:{'null' if null else 'real'}:"
    c = [r for r in evals.values() if r["genome"]["null"] == null and (r["origin"] == "pool" or r["origin"].startswith(tag))]
    return max(c, key=lambda r: Z.fitness(r, train))

if __name__ == "__main__":
    out = Z.HERE / "results.json"
    if out.exists():
        raise SystemExit("scored once already")
    E = Z.load_evals()
    res = {"loyo": {}}
    for y in Z.YEARS:
        res["loyo"][y] = {k: {"genome": (p := pick(E, y, k == "null"))["genome"], "heldout": p["years"][y],
                              "train_fitness": round(Z.fitness(p, Z.folds()[y]), 1)} for k in ("real", "null")}
    real = [res["loyo"][y]["real"]["heldout"]["net"] for y in Z.YEARS]
    null = [res["loyo"][y]["null"]["heldout"]["net"] for y in Z.YEARS]
    fin = pick(E, "ALL", False)
    res["final"] = {"genome": fin["genome"], "years": fin["years"]}
    chk = {"heldout_positive": sum(x > 0 for x in real), "heldout_sum": round(sum(real)), "null_sum": round(sum(null)),
           "final_years_positive": sum(fin["years"][y]["net"] > 0 for y in Z.YEARS)}
    chk["verdict"] = "PROMISING (paper/forward only)" if (chk["heldout_positive"] >= 3 and chk["heldout_sum"] > 0
        and chk["heldout_sum"] > chk["null_sum"] and chk["final_years_positive"] == 4) else "NOT PROVEN"
    res["checks"] = chk
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(chk, indent=1))
    for y in Z.YEARS:
        for k in ("real", "null"):
            h = res["loyo"][y][k]["heldout"]
            print(y, k, h["net"], "won/lost/active", h["green"], h["red"], h["active"], "of", h["sessions"], "trades", h["trades"])
    print("final", {y: (fin["years"][y]["net"], fin["years"][y]["green"], fin["years"][y]["red"], fin["years"][y]["active"]) for y in Z.YEARS})
    print(fin["genome"])
