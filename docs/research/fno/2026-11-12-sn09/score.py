"""SN09: the frozen rule once; then the honest combination (N11 days -> N11, other days -> each fold's held-out pick)."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn09 as Z
B = Z.B

def pick(E, fold, null):
    train = tuple(y for y in Z.YEARS if y != fold) if fold != "ALL" else Z.YEARS
    tag = f"ga:{fold}:{'null' if null else 'real'}:"
    c = [r for r in E.values() if r["genome"]["null"] == null and (r["origin"] == "pool" or r["origin"].startswith(tag))]
    return max(c, key=lambda r: Z.fitness(r, train))

if __name__ == "__main__":
    out = HERE / "results.json"
    if out.exists():
        raise SystemExit("scored once already")
    E = Z.load_evals()
    res = {"loyo": {y: {k: {"genome": (p := pick(E, y, k == "null"))["genome"], "heldout": p["years"][y]} for k in ("real", "null")} for y in Z.YEARS}}
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
        print(y, {k: (round(res["loyo"][y][k]["heldout"]["net"]), res["loyo"][y][k]["heldout"]["active"], res["loyo"][y][k]["heldout"]["sessions"]) for k in ("real", "null")})
    print("final", {y: (round(fin["years"][y]["net"]), fin["years"][y]["active"]) for y in Z.YEARS}, fin["genome"])
    combo = {}
    for y in Z.YEARS:
        Y = B.Year(y); n11 = Y.sigs("N11"); oi = Z.O.load(y); g = res["loyo"][y]["real"]["genome"]
        nets = []
        for S in Y.ordered():
            if S.day in n11:
                nets.append(B.play_day(S, n11[S.day], {}, 15000.0, 3000.0)["net"])
            else:
                S.oi = oi.get(S.day, {}); nets.append(Z.run_day(S, g)["net"])
        combo[y] = {"net": round(sum(nets)), "won": sum(x > 0 for x in nets), "lost": sum(x < 0 for x in nets),
                    "none": sum(x == 0 for x in nets), "refilled": round(sum(-x for x in nets if x < 0))}
    res["combo_heldout"] = combo
    print("combo held out", combo, "total", sum(combo[y]["net"] for y in Z.YEARS))
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
