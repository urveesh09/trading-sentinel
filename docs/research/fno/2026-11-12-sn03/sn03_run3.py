"""SN03 round 3: confirm before buying; leave trades that are not working."""
import json
import sn03 as Z
from sn03_run import loyo, show

if __name__ == "__main__":
    years = {y: Z.Year(y) for y in Z.YEARS}
    F = {"benchmark": {}}
    for d in (1, 2, 3, 5):
        for x in (0.0, 0.02, 0.05):
            F[f"confirm {d}m, option +{int(x*100)}%"] = {"confirm_d": d, "confirm_x": x}
    for n in (5, 10, 15, 20, 30):
        for x in (-0.05, 0.0, 0.03):
            F[f"leave at {n}m if below {int(x*100):+d}%"] = {"work_n": n, "work_x": x}
    res = {"F": {k: {y: Z.year_result(years[y], v) for y in Z.YEARS} for k, v in F.items()}}
    show("F", res["F"])
    for obj in ("profit", "calm"):
        L = loyo(res["F"], obj)
        res[f"loyo_{obj}"] = L
        print(f"LOYO F {obj:6s}", {y: (L[y]["pick"], L[y]["net"]) for y in Z.YEARS}, "sum", L["sum"], flush=True)
    Z.HERE.joinpath("_local", "round3.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
