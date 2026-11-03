"""The final evidence for E03, every figure on the four-strike pick: E02 R3 and E03 at three fill
levels, the runner's neighbours, a random-entry control and the recorded Production sessions."""
import json, random, sys
import numpy as np
import e03_lab as X
import controls as C
import native as N
E = X.E

E03 = dict(max_lots=3, split=True, runner_floor=1.0, runner_keep=0.5, hero_target=9.0)
NEIGHBOURS = {"K40": dict(runner_keep=.4), "K60": dict(runner_keep=.6), "F12": dict(runner_floor=1.2),
              "T4": dict(hero_target=4.0), "TNONE": dict(hero_target=0.0), "L2": dict(max_lots=2)}


def main(seeds=40):
    out = dict(candidate={**X.R3, **E03}, rules={}, neighbours={}, random={}, native={})
    for name, extra in (("E02_R3", {}), ("E02_2LOT", dict(max_lots=2)), ("E03", E03)):
        rule = X.Hero(**{**X.R3, **extra})
        for y in (2024, 2025):
            for sc in ("ordinary", "adverse", "catastrophe"):
                r = X.run_year(X.tapes(y), rule, sc, details=sc == "ordinary")
                out["rules"][f"{name}|{y}|{sc}"] = dict(summary=r["summary"], days=[dict(day=d["day"], net=d["net"], trades=d["trades"],
                    positions=[dict(symbol=p["symbol"], entry=p["entry"], lots=p["lots"], peak=p["peak"], net=p["net"],
                                    exits=[(e.get("reason"), e["price"], e["lots"]) for e in p["events"][1:]]) for p in d["positions"]])
                    for d in r["days"] if d["trades"]] if sc == "ordinary" else [])
                print(name, y, sc, X.brief(r["summary"]), flush=True)
    for name, extra in NEIGHBOURS.items():
        rule = X.Hero(**{**X.R3, **E03, **extra})
        for y in (2024, 2025):
            for sc in ("ordinary", "adverse"):
                out["neighbours"][f"{name}|{y}|{sc}"] = X.brief(X.run_year(X.tapes(y), rule, sc)["summary"])
                print("neighbour", name, y, sc, out["neighbours"][f"{name}|{y}|{sc}"]["net"], flush=True)
    for name, extra in (("E02_R3", {}), ("E03", E03)):
        rule = X.Hero(**{**X.R3, **extra})
        for y in (2024, 2025):
            actual = out["rules"][f"{name}|{y}|ordinary"]["summary"]["net"]
            nets = []
            try:
                for s in range(seeds):
                    E.directions = C.random_directions(s)
                    nets.append(X.run_year(X.tapes(y), rule)["summary"]["net"])
            finally:
                E.directions = C.ORIGINAL
            nets = np.array(nets)
            out["random"][f"{name}|{y}"] = dict(actual=actual, seeds=seeds, mean=round(float(nets.mean()), 2),
                                                 p95=round(float(np.percentile(nets, 95)), 2), share_at_or_above=float((nets >= actual).mean()))
            print("random", name, y, out["random"][f"{name}|{y}"], flush=True)
    ts = N.tapes()
    for name, extra in (("E02_R3", {}), ("E03", E03)):
        for sc in ("ordinary", "adverse"):
            r = X.run_year(ts, X.Hero(**{**X.R3, **extra}), sc)
            out["native"][f"{name}|{sc}"] = dict(sessions=[t.day for t in ts], summary=X.brief(r["summary"]))
    X.D.dump(X.HERE / "final-results.json", out)
    print("FINAL_DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
