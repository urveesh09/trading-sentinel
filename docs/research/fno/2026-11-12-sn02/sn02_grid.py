"""SN02-A grid: N11 entries inside the Rs 15,000 SN01 wallet (fixed wallet, target 1,500, loss limit 3,000)."""
import json, sys
from collections import Counter
import sn02_ext as X

VARIANTS = {}
for ex, give in (("n11", 0.0), ("sell", 0.0), ("lock", 0.25), ("lock", 0.5), ("lock", 1.0), ("lock", 2.0)):
    for lots in (1, 2):
        for fb in (False, True):
            VARIANTS[f"{ex}{'' if ex != 'lock' else give}|L{lots}|{'otm' if fb else 'skip'}"] = {
                "exit": ex, "give": give, "max_lots": lots, "cash": 1.0, "otm_fallback": fb}

def run(years=X.YEARS, stresses=(0.0, 100.0, 205.0)):
    out = {}
    for y in years:
        Y = X.Year(y)
        for name, v in VARIANTS.items():
            for s in stresses:
                R = [X.play_day(S, Y.sigs.get(S.day, []), v, 15000.0, 1500.0, 3000.0, s) for S in Y.ordered()]
                sk = Counter(k for r in R for k in r["skipped"])
                out.setdefault(name, {}).setdefault(str(int(s)), {})[y] = {
                    "net": round(sum(r["net"] for r in R)), "trades": sum(r["trades"] for r in R),
                    "trade_days": sum(1 for r in R if r["trades"]), "target_days": sum(1 for r in R if r["end"] == "target"),
                    "green": sum(1 for r in R if r["net"] > 0), "red": sum(1 for r in R if r["net"] < 0),
                    "worst": round(min(r["net"] for r in R)), "skipped": dict(sk)}
    return out

if __name__ == "__main__":
    res = run()
    (X.HERE / "_local").mkdir(exist_ok=True)
    (X.HERE / "_local" / "grid.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    for name, by in res.items():
        print(f"{name:22s}", " | ".join(f"+{s}: " + " ".join(f"{by[s][y]['net']:>7}" for y in X.YEARS) + f" = {sum(by[s][y]['net'] for y in X.YEARS):>7}" for s in by))
    v = res["n11|L1|skip"]["205"]
    print({y: (v[y]["trades"], v[y]["trade_days"], v[y]["target_days"], v[y]["skipped"]) for y in X.YEARS})
    v = res["lock0.5|L1|otm"]["205"]
    print({y: (v[y]["trades"], v[y]["trade_days"], v[y]["target_days"], v[y]["skipped"]) for y in X.YEARS})
