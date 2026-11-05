"""Apply the original N012 development gates to complete Round 22 receipts."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
YEARS = tuple(str(y) for y in range(2022, 2027))
CONTROLS = ("N11", "N11T")
CANDIDATES = ("ACCEPT_15", "REJECT_15")


def net(panels, name):
    return sum(panel[name]["net"] for panel in panels.values())


def compare(panels, name):
    reference = max(CONTROLS, key=lambda arm: net(panels, arm))
    total, target = net(panels, name), 1.20 * net(panels, reference)
    paired = {}
    annual = {}
    for year, panel in panels.items():
        candidate, baseline = panel[name], panel[reference]
        for row in (candidate, baseline):
            assert abs(sum(row["daily"].values()) - row["net"]) <= .011
        annual[year] = round(candidate["net"] - baseline["net"], 2)
        dates = candidate["daily"].keys() | baseline["daily"].keys()
        assert all(day.startswith(year) for day in dates) and not (paired.keys() & dates)
        for day in dates:
            paired[day] = candidate["daily"].get(day, 0.) - baseline["daily"].get(day, 0.)
    best = sorted(((d, v) for d, v in paired.items() if v > 0), key=lambda item: (-item[1], item[0]))[:5]
    paired_net = sum(paired.values())
    assert abs(paired_net - (total - net(panels, reference))) <= .051
    after_best = paired_net - sum(value for _, value in best)
    day = min(p[name]["worst_day"] for p in panels.values())
    reference_day = min(p[reference]["worst_day"] for p in panels.values())
    drawdown = max(p[name]["drawdown_pct"] for p in panels.values())
    reference_drawdown = max(p[reference]["drawdown_pct"] for p in panels.values())
    gates = {
        "20_percent_net_improvement": total >= target,
        "worst_day": day >= reference_day - 1000.,
        "max_annual_closed_drawdown": drawdown <= reference_drawdown + 1.,
        "annual_net_floor": all(value >= -2500. for value in annual.values()),
        "after_best_five_incremental_days": after_best > 0.,
        "no_unresolved_exposure": all(p[name]["unresolved"] == 0 for p in panels.values()),
    }
    return {"control": reference, "control_net": round(net(panels, reference), 2), "net": round(total, 2),
            "net_target": round(target, 2), "annual_delta": annual, "worst_day": day, "control_worst_day": reference_day,
            "max_drawdown_pct": drawdown, "control_max_drawdown_pct": reference_drawdown,
            "paired_increment": round(paired_net, 2), "increment_after_best_five": round(after_best, 2),
            "removed_days": best, "gates": gates, "provisional_development_pass": all(gates.values()),
            "untouched_validation": "NOT_SCORED", "doubled_stress": "NOT_SCORED", "qualified": False}


def main():
    panels = {year: json.loads((HERE / f"round22-{year}.json").read_bytes()) for year in YEARS}
    value = {candidate: compare(panels, candidate) for candidate in CANDIDATES}
    with (HERE / "round22-gates.json").open("x", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print(json.dumps(value, indent=2), flush=True)


if __name__ == "__main__":
    main()
