"""November 5 regular F&O check on the production paper receipts."""
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

from capital_audit import mirror

DAY = date(2026, 11, 5).isoformat()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    mode = "x"
    if path.parent.name == "modules":
        assert read(path)["status"] == "NOT_RUN"
        mode = "w"
    with path.open(mode, encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main(folder):
    sealed = read(folder / "inputs.json")["files_sha256"]
    for path, expected in sealed.items():
        assert hashlib.sha256((folder / path).read_bytes()).hexdigest() == expected
    live = read(folder / "_local/regular.json")
    paths = read(folder / "_local/regular-today-results.json")
    rows = live["positions"]
    assert len(rows) == len(paths["today"]) == 3
    for row in rows:
        paired = paths["today"][str(row["id"])]
        assert row["entry_date"] == DAY and paired["parity"]
        assert paired["N11T"]["exit_time"] == row["exit_time"]
        assert paired["N11T"]["exit"] == row["exit_premium"]
        assert abs(paired["N11T"]["net"] - row["pnl"]) <= .01
    control = round(sum(row["pnl"] for row in rows), 2)
    spread = round(sum(row["pnl"] for row in live["spreads"]), 2)
    assert control == 4821.18 and spread == 2545.91
    mirror_rows = [{**row, "initial_entry_time": row["entry_time"], "initial_entry_premium": row["entry_premium"]}
                   for row in rows]
    lot, = set(row["lot_size"] for row in rows)
    scenarios = {f"{start}-{label}": mirror(mirror_rows, start, lot, adverse)
                 for start in (12500, 15000) for label, adverse in (("standard", False), ("adverse", True))}
    write(folder / "regular-capital-nov5.json", {
        "paper_singles": control, "paper_defined_risk_recorded": spread,
        "paper_regular_total_recorded": round(control + spread, 2), "mirrors": scenarios,
        "held_exit_parity": len(rows), "notes": "Conditional reprice of recorded parent admissions and exits.",
    })
    metrics = {"filled_fee_pnl": control, "assumed_pnl": 0., "modeled_net": control,
               "closed_trades": len(rows), "unresolved": 0, "signals": None}
    write(folder / "modules/fno_nifty_single.json", {
        "module": "fno_nifty_single", "start": DAY, "end": DAY, "population": "PRIMARY",
        "status": "PARTIAL", "coverage": "PARTIAL", "fidelity": "QUOTE_LIFECYCLE",
        "reason": "Three recorded paper exits reconciled. Wallet scenarios are conditional on production admissions and exits.",
        "inputs": ["configuration.json", "_local/regular.json", "_local/regular-today-results.json"],
        "artifacts": ["regular-capital-nov5.json"],
        "assumptions": ["Opening trial wallet is flat at ₹12,500 or ₹15,000, fees recomputed for one lot."],
        "limitations": ["No alternative entry lifecycle. No live re-quote, broker queue or resting-stop execution."],
        "metrics": metrics, "daily_results": [{"date": DAY, "status": "PARTIAL", "metrics": metrics}],
    })
    for module in ("fno_sensex_single", "fno_defined_risk"):
        row = read(folder / f"_local/{module}.json")
        row["inputs"] = ["configuration.json", "_local/regular.json"]
        write(folder / f"modules/{module}.json", row)
    print({key: (val["closed"], val["net"], val["rejects"]) for key, val in scenarios.items()})


if __name__ == "__main__":
    main(Path(sys.argv[1]))
