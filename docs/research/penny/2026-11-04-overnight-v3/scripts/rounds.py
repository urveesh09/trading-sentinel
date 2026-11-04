"""Score a round's arms on the four development panels under the seven frozen fill models."""
import json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import v3sim as v
MODELS = {"M1": v.FillModel("M1"), "M2": v.FillModel("M2", win_fill=.75), "M3": v.FillModel("M3", win_fill=.5),
          "M4": v.FillModel("M4", win_fill=.5, correlated=True), "M5": v.FillModel("M5", kappa=.001),
          "M6": v.FillModel("M6", win_fill=.5, kappa=.001), "M7": v.FillModel("M7", exit_bps=20.)}
SEEDS = [20261104 + k for k in range(10)]
ROUNDS = {
    2: [v.Policy("V2"), v.Policy("NIGHT10", rank="night"), v.Policy("NIGHTALL", depth=None, rank="night"),
        v.Policy("NIGHTALL_HI", depth=None, rank="night_hi20"), v.Policy("NIGHTALL_CAP", depth=None, rank="night", cap_kappa=.001)],
    3: [v.Policy("V2"), v.Policy("V2_HI", rank="strength_hi20"), v.Policy("V2_Q4", night_min=.004),
        v.Policy("ALL_HI", depth=None, rank="strength_hi20"), v.Policy("CAPRANK", depth=None, rank="night_cap")],
    4: [v.Policy("V2"), v.Policy("V2_HI", rank="strength_hi20"),
        v.Policy("V2_HI_F3N", rank="strength_hi20", filler="F3", filler_order="night"),
        v.Policy("V2_HI_F3L", rank="strength_hi20", filler="F3", filler_order="value"),
        v.Policy("F3_ONLY_HI", rank="strength_hi20", filler="F3", filler_order="night", edge_pool=False),
        v.Policy("V2_HI_F5L", rank="strength_hi20", filler="F5", filler_order="value")],
}
def run(rnd, extra=None):
    P = v.load_days()
    arms = ROUNDS[rnd] if extra is None else extra
    res = {}
    for panel, (days, s, e) in P.items():
        for p in arms:
            row = {}
            for m, fm in MODELS.items():
                seeds = SEEDS if fm.win_fill < 1 else [SEEDS[0]]
                runs = [v.simulate(days, p, fm, start=s, end=e, keep=(m == "M1"), seed=sd) for sd in seeds]
                r = runs[0]
                sm = r["summary"]
                nets = [x["summary"]["net"] for x in runs]
                row[m] = {"net": round(sum(nets) / len(nets)), "net_seed0": round(nets[0]), "net_min_seed": round(min(nets)),
                          "dd": round(max(x["summary"]["dd"] for x in runs)), "closes": sm.get("n"),
                          "pf": sm.get("pf"), "open_at_end": max(x["open_at_end"] for x in runs)}
                if m == "M1":
                    row["years"] = v.by_year(r["trades"]); row["outcomes"] = r["outcomes"]
            row["robust"] = min(row[m]["net"] for m in MODELS)
            res[f"{panel}|{p.name}"] = row
            print(f"{panel:5s} {p.name:14s} " + " ".join(f"{m}:{row[m]['net']:>8}" for m in MODELS) + f"  robust:{row['robust']:>8} dd1:{row['M1']['dd']}", flush=True)
    return res
if __name__ == "__main__":
    rnd = int(sys.argv[1])
    t = time.time(); res = run(rnd)
    (HERE / "results").mkdir(exist_ok=True)
    json.dump(res, open(HERE / f"results/round{rnd}.json", "w"), indent=1)
    print("seconds", round(time.time() - t))
