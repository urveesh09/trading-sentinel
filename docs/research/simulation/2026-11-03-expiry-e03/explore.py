"""Named hand-built variants, both seen years, ordinary and adverse. Every run is appended to the ledger."""
import csv, json, sys, time
from dataclasses import asdict
from pathlib import Path
import e03_lab as X

LEDGER = X.HERE / "trials-explore.csv"


def evaluate(name, rule, scenarios=("ordinary", "adverse")):
    out = {}
    for y in (2024, 2025):
        for s in scenarios:
            out[f"{y}_{s}"] = X.brief(X.run_year(X.tapes(y), rule, s)["summary"])
    new = not LEDGER.exists()
    with LEDGER.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["at", "name", "key", *[f"{k}_{m}" for k in out for m in ("net", "without_best", "worst", "trades")], "rule_json"])
        w.writerow([time.strftime("%H:%M:%S"), name, rule.key, *[out[k][m] for k in out for m in ("net", "without_best", "worst", "trades")],
                    json.dumps(asdict(rule), sort_keys=True)])
    return out


def show(name, out):
    cells = "  ".join(f"{k}: {v['net']:>9.0f} xb {v['without_best']:>8.0f} w {v['worst']:>6.0f} n {v['trades']:>3}" for k, v in out.items())
    print(f"{name:<22} {cells}", flush=True)


if __name__ == "__main__":
    variants = json.loads(Path(sys.argv[1]).read_text())
    for name, extra in variants.items():
        rule = X.Hero(**{**X.R3, **extra})
        show(name, evaluate(name, rule))
