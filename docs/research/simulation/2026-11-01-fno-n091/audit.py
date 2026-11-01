"""Independent receipt/financial/state audit. No strategy decisions are regenerated here."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
sys.path.insert(0, str(ROOT / "python-engine"))
from fno_costs import calc_fno_costs

LOCAL = HERE / "_local"
OLD = HERE.parent / "2026-11-01-fno-n09/_local"
YEARS = ("2023", "2024", "2025", "2026")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def controls():
    report = {}
    for y in YEARS:
        new = read(LOCAL / f"keys-controls-{y}.json")
        diag, panel = read(OLD / f"keys-diag-{y}.json"), read(OLD / f"keys-panel-{y}.json")
        for name in ("N08", "DIAG", "S_VOL"):
            old_key = panel["CASH|S_VOL"] if name == "S_VOL" else diag[name]
            fresh = read(LOCAL / f"evals/{new[name]}.json")
            old = read(OLD / f"evals-{y}/{old_key}.json")
            assert fresh["trades"] == old["trades"], (y, name, "exact trade parity failed")
            report[y + "|" + name] = {"exact": True, "trades": len(fresh["trades"]),
                "net": sum(t["net_pnl"] for t in fresh["trades"]),
                "old_sha256": hashlib.sha256((OLD / f"evals-{y}/{old_key}.json").read_bytes()).hexdigest(),
                "new_sha256": hashlib.sha256((LOCAL / f"evals/{new[name]}.json").read_bytes()).hexdigest()}
    (HERE / "control-parity.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("EXACT_CONTROLS", len(report), sum(r["trades"] for r in report.values()))


def full():
    counts = Counter()
    ends = {}
    states = {}
    report = {}
    for phase in ("controls", "primary", "costs", "carry"):
        if phase == "carry":
            states = {}
        for year in YEARS:
            keys = read(LOCAL / f"keys-{phase}-{year}.json")
            for name, key in keys.items():
                obj = read(LOCAL / f"evals/{key}.json")
                book, trades = obj["book"], obj["trades"]
                trace = read(LOCAL / f"receipts/{key}.json")
                admissions = trace["admissions"]
                accepted = [a for a in trace["decisions"] if a["outcome"] == "accepted"]
                assert len(accepted) == len(trades), (phase, year, name, "accepted signals differ from positions")
                a, b = book.get("cost") or (0., 0.)
                equity = ends.get(name, 250000.) if phase == "carry" else 250000.
                opening = equity
                for t in sorted(trades, key=lambda r: r["exit_time"]):
                    assert t["status"] == "CLOSED"
                    assert t.get("adds", 0) == 0 and not t.get("fills"), "unsupported partial/pyramid lifecycle"
                    qty, lots = t["initial_quantity"], t["lots_at_exit"]
                    assert qty == t["entry_qty"] == lots * 65
                    assert 1 <= lots <= (1 if name == "DIAG" else 2)
                    assert t["initial_entry_time"] == t["entry_time"]
                    assert t["initial_entry_premium"] == t["entry_premium"]
                    entry, exit = datetime.fromisoformat(t["entry_time"]), datetime.fromisoformat(t["exit_time"])
                    bar = datetime.fromisoformat(t["bar_ts"]).replace(tzinfo=entry.tzinfo)
                    assert bar + timedelta(minutes=5) <= entry < exit
                    assert entry.date() == exit.date(), "new overnight position"
                    gross = (t["exit_premium"] - t["entry_premium"]) * qty
                    fees = calc_fno_costs(t["entry_premium"], t["exit_premium"], qty)
                    extra = (a + b * lots) * lots
                    assert abs(t["gross_pnl"] - gross) < .001
                    assert abs(t["extra_cost"] - extra) < .001
                    assert abs(t["net_pnl"] - gross + fees + extra) < .001
                    assert qty * t["entry_premium"] <= equity + .001
                    matches = [r for r in accepted if r["at"] == t["entry_time"] and r["bar_ts"] == t["bar_ts"]]
                    assert len(matches) == 1
                    if book.get("n091"):
                        linked = [r for r in admissions if r.get("admission_id") == t["admission_id"]]
                        assert len(linked) == 1
                        r = linked[0]
                        assert r["accepted"] and r["final_lots"] == lots
                        assert r["ask"] == t["entry_premium"] and r["symbol"] == t["tradingsymbol"]
                        assert r["stop"] == t["initial_stop_underlying"] and r["target"] == t["initial_target_underlying"]
                        assert t["n091_entry"]["pool"] == r["pool"]
                        assert r["final_lots"] <= r["native_lots"] <= 2
                        if t["origin"] == "TPB_LOW" and entry.hour >= 12:
                            assert lots == 1, "N08 noon ceiling was expanded"
                        if book["n091"]["mode"] == "CUSHION":
                            cost_upper = calc_fno_costs(t["entry_premium"], t["entry_premium"], qty)
                            worst_loss = t["entry_premium"] * qty + cost_upper + extra
                            assert abs(r["full_reserves"][str(lots)] - worst_loss) < 1e-7
                            assert r["pool"] - r["open_reserve"] - worst_loss >= r["floor"] - .001
                            assert t["net_pnl"] >= -worst_loss - .001
                            assert r["floor"] >= 212500. - .001
                            assert r["pool"] + t["net_pnl"] >= r["floor"] - .001
                            counts["funded_full_premium_admissions"] += 1
                        counts["immutable_budget_admission_bindings"] += 1
                    equity += t["net_pnl"]
                    counts["financial_lifecycles"] += 1
                if phase == "carry":
                    ends[name] = equity
                if book.get("n091"):
                    state = read(LOCAL / f"states/{key.rsplit('_', 1)[-1]}.json")
                    assert abs(state["start_equity"] - opening) < .001
                    assert abs(state["end_equity"] - equity) < .01
                    if book["n091"]["mode"] == "CUSHION":
                        floors = [r["floor"] for r in admissions]
                        assert floors == sorted(floors), "floor decreased within year"
                        assert state["budget"]["floor"] >= max(floors or [212500.]) - .001
                        if phase == "carry" and name in states:
                            assert state["previous"] == states[name]["digest"]
                            assert state["budget"]["floor"] >= states[name]["floor"] - .001
                        states[name] = {"digest": key.rsplit('_', 1)[-1], "floor": state["budget"]["floor"]}
                    counts["persisted_cash_state_checks"] += 1
                for r in admissions:
                    assert r["native_lots"] >= r["final_lots"] >= 0
                    if r["floor"] is not None:
                        costs = {int(k): v for k, v in r["full_reserves"].items()}
                        fits = [n for n, risk in costs.items() if r["floor"] + r["open_reserve"] + risk <= r["pool"] + 1e-8]
                        assert r["final_lots"] == max(fits, default=0)
                    counts["budget_decisions"] += 1
                counts["annual_books"] += 1
                report[phase + "|" + year + "|" + name] = {"start": opening, "end": equity, "trades": len(trades)}
    assert counts["annual_books"] == 60
    result = {"status": "INDEPENDENT_CASH_ADMISSION_CHECKS_PASSED", "counts": dict(counts), "books": report,
              "continuous_ends": ends, "limits": ["candle execution/fees assumptions", "no fresh broker fills", "no proof of profitable strategy"]}
    (HERE / "audit-results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": dict(counts), "continuous_ends": ends}, indent=2))


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("phase", choices=("controls", "full"))
    args = cli.parse_args()
    (controls if args.phase == "controls" else full)()
