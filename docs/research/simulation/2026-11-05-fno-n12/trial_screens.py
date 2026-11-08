"""Check two ₹15,000 entry-risk screens on the sealed conditional mirror."""
import hashlib
import json
from pathlib import Path
import subprocess

from anatomy import DATASETS, read, trades
from capital_audit import mirror, calc_fno_costs, entry_limit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def selected(trade, lot, arm):
    entry = float(trade["initial_entry_premium"])
    limit = entry_limit(entry * 1.01, .05, 2, entry * 1.02)
    if limit is None:
        return False
    if arm == "CASH_BUFFER":
        return limit * lot + calc_fno_costs(limit, 0., lot) <= 9750.
    delta = trade.get("delta_at_entry")
    if delta is None or not 0 < abs(delta) <= 1:
        return False
    side = 1 if trade["direction"] == "LONG" else -1
    distance = side * (trade["entry_underlying"] - trade["initial_stop_underlying"])
    if distance <= 0:
        return False
    modeled_exit = limit - min(.25 * limit, 1.75 * abs(delta) * distance)
    return (limit - modeled_exit) * lot + calc_fno_costs(limit, modeled_exit, lot) + 205. <= 1500.


def main():
    freeze = HERE / "trial-freeze.json"
    spec = read(freeze)
    assert spec == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{freeze.relative_to(ROOT).as_posix()}"], cwd=ROOT,
    ))
    for name, sha in spec["files"].items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == sha
    controls = read(HERE / "round1-freeze.json")
    earlier = read(HERE / "capital-results.json")
    out = {}
    for year, root in DATASETS.items():
        manifest = root / "manifest.json"
        assert hashlib.sha256(manifest.read_bytes()).hexdigest() == controls["data_manifest_sha256"][year]
        source, raw = trades(year, "N11T")
        assert hashlib.sha256(source.read_bytes()).hexdigest() == controls["controls_sha256"][year]["N11T"]
        rows = raw["trades"]
        lot = int(read(manifest)["lot_size"])
        out[year] = {}
        for adverse in (False, True):
            label = "adverse" if adverse else "standard"
            out[year][label] = {}
            for arm in ("CONTROL", "CASH_BUFFER", "STOP_BUDGET"):
                chosen = rows if arm == "CONTROL" else [trade for trade in rows if selected(trade, lot, arm)]
                result = mirror(chosen, 15000, lot, adverse)
                result.pop("decisions")
                result.pop("trades")
                if arm == "CONTROL":
                    assert result == earlier[year]["trial"][f"15000-{label}"]
                result["screened_before_wallet"] = len(rows) - len(chosen)
                out[year][label][arm] = result
                print(year, label, arm, result["closed"], result["net"], result["worst_day"],
                      result["closed_drawdown_pct"], result["screened_before_wallet"], flush=True)
    with (HERE / "trial-results.json").open("x", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2, sort_keys=True)
        handle.write("\n")


if __name__ == "__main__":
    main()
