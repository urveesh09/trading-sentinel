"""SN03 runner: benchmark parity, concept families B/C/D, leave-one-year-out picks, then E and the wallet caps."""
import json, sys, time
import sn03 as Z

def families():
    B = {"none": None}
    for x in (["OR20"], ["EFF"], ["SHIPPED"], ["OR20", "SHIPPED"], ["EFF", "SHIPPED"]):
        B["drop " + "+".join(x)] = {"kind": "expert_not", "value": x}
    B["TPB only"] = {"kind": "expert_only", "value": ["TPB"]}
    B["puts only"] = {"kind": "side", "value": "PE"}
    B["calls only"] = {"kind": "side", "value": "CE"}
    for hhmm, m in (("11:00", 105), ("12:30", 195), ("14:00", 285)):
        B[f"enter before {hhmm}"] = {"kind": "before", "value": m}
    B["enter after 10:00"] = {"kind": "after", "value": 45}
    for d in (2, 3):
        B[f"expiry >= {d} days"] = {"kind": "dte_min", "value": d}
    B["expiry <= 2 days"] = {"kind": "dte_max", "value": 2}
    B["ADX gate HIGH"] = {"kind": "gate", "value": ":HIGH"}
    B["ADX gate LOW"] = {"kind": "gate", "value": ":LOW"}
    C = {"none": {}}
    for be in (300, 500, 750, 1000, 1500):
        C[f"breakeven after +{be}"] = {"be": be}
    for tp in (500, 750, 1000, 1500, 2000, 3000):
        C[f"quick profit +{tp}"] = {"tp": tp}
    for at in (750, 1500):
        for give in (0.3, 0.5):
            C[f"trail after +{at} give {give}"] = {"trail_at": at, "trail_give": give}
    for h in (0.15, 0.20, 0.30):
        C[f"hard stop -{int(h*100)}%"] = {"hard": h}
    D = {"N11": ("N11",), "NO_STAND": ("NO_STAND",), "N11+NO_STAND": ("N11", "NO_STAND"),
         "R0.85": ("R0.85",), "N15": ("N15",), "N25": ("N25",), "NO_LOSS": ("NO_LOSS",),
         "N11+R0.85+N15": ("N11", "R0.85", "N15")}
    return B, C, D

def score(per, train, objective):
    s = sum(per[y]["net"] for y in train)
    if objective == "calm":
        s -= 500 * sum(per[y]["red"] for y in train)
    return s

def loyo(table, objective):
    out = {}
    for held in Z.YEARS:
        train = [y for y in Z.YEARS if y != held]
        pick = max(table, key=lambda k: score(table[k], train, objective))
        out[held] = {"pick": pick, **table[pick][held]}
    out["sum"] = {"net": sum(out[y]["net"] for y in Z.YEARS), "red": sum(out[y]["red"] for y in Z.YEARS),
                  "green": sum(out[y]["green"] for y in Z.YEARS)}
    return out

def show(name, table):
    for k, per in table.items():
        tot = {f: sum(per[y][f] for y in Z.YEARS) for f in ("net", "green", "red", "none", "refilled", "trades")}
        print(f"  {name:3s} {k:28s} net {tot['net']:>8}  " + " ".join(f"{per[y]['net']:>7}" for y in Z.YEARS)
              + f"  won/lost/none {tot['green']}/{tot['red']}/{tot['none']}  refill {tot['refilled']}  trades {tot['trades']}", flush=True)

if __name__ == "__main__":
    t0 = time.time()
    years = {y: Z.Year(y) for y in Z.YEARS}
    res = {}
    B, C, D = families()
    base = {y: Z.year_result(years[y], {}) for y in Z.YEARS}
    print("benchmark", {y: base[y]["net"] for y in Z.YEARS}, sum(base[y]["net"] for y in Z.YEARS), flush=True)
    res["B"] = {k: {y: Z.year_result(years[y], {"filter": f}) for y in Z.YEARS} for k, f in B.items()}
    # random-drop control at the share each filter drops
    res["C"] = {k: {y: Z.year_result(years[y], v) for y in Z.YEARS} for k, v in C.items()}
    res["D"] = {k: {y: Z.year_result(years[y], {}, books=b) for y in Z.YEARS} for k, b in D.items()}
    for fam in ("B", "C", "D"):
        show(fam, res[fam])
    res["loyo"] = {fam: {obj: loyo(res[fam], obj) for obj in ("profit", "calm")} for fam in ("B", "C", "D")}
    for fam in ("B", "C", "D"):
        for obj in ("profit", "calm"):
            L = res["loyo"][fam][obj]
            print(f"LOYO {fam} {obj:6s}", {y: (L[y]["pick"], L[y]["net"]) for y in Z.YEARS}, "sum", L["sum"], flush=True)
    Z.HERE.joinpath("_local").mkdir(exist_ok=True)
    Z.HERE.joinpath("_local", "round1.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("seconds", round(time.time() - t0))
