"""Reproduce frozen Round 22 decisions for its three largest native-book losses."""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess

import round22 as study


HERE = Path(__file__).resolve().parent
r, Y = study.r, study.Y
YEARS = tuple(str(year) for year in range(2022, 2027))


def day_residuals(panels):
    residuals = {}
    for panel in panels:
        sleeve = defaultdict(float)
        for trade in panel["extra_trades"][study.ACCEPT]:
            if trade["status"] != "CLOSED":
                raise ValueError("cannot attribute unsettled sleeve cash")
            sleeve[trade["exit_time"][:10]] += trade["net_pnl"]
        accept = panel[study.ACCEPT]["daily"]
        control = panel["N11T"]["daily"]
        for day in accept.keys() | control.keys() | sleeve.keys():
            residuals[day] = {"n11t_net": control.get(day, 0.0), "accept_net": accept.get(day, 0.0),
                              "sleeve_net": sleeve[day],
                              "native_delta": accept.get(day, 0.0) - sleeve[day] - control.get(day, 0.0)}
    return residuals


class TraceEntry:
    def _entry(self, book, obs, frame, day, now):
        if day not in self.trace_days:
            return super()._entry(book, obs, frame, day, now)
        prior = len(self.decisions)
        next_id = book.next_id
        held = [{"id": leg.id, "member": self.leg_member[leg.id], "symbol": leg.tradingsymbol, "qty": leg.qty}
                for leg in book.open.values()]
        pool = book.equity
        realized = sum(value for at, value, _kind in book.closes if at.date() == now.date() and at <= now)
        notes = self.notes.copy()
        funnel = self.funnel.copy()
        super()._entry(book, obs, frame, day, now)
        if self._fired is None and not self.decisions[prior:] and notes["n11_stood_aside"] == self.notes["n11_stood_aside"]:
            return
        filled = book.open.get(next_id) if book.next_id != next_id else None
        self.trace[day].append({
            "at": now.isoformat(), "member": self._fired, "held": held,
            "open_premium": round(sum(leg.entry_premium * leg.qty for leg in book.open.values()
                                      if leg.id < next_id), 4),
            "pool": round(pool, 4), "realized_day": round(realized, 4),
            "planner": self.decisions[prior:], "funnel_change": dict(self.funnel - funnel),
            "notes_change": dict(self.notes - notes),
            "filled": None if filled is None else {
                "symbol": filled.tradingsymbol, "qty": filled.qty, "premium": filled.entry_premium,
                "bar": filled.bar_ts, "direction": filled.direction,
                "n11": getattr(filled, "_n11", None),
            },
        })


class AcceptanceTrace(TraceEntry, study.SlowReplay):
    pass


class ControlTrace(TraceEntry, Y.BookReplay):
    pass


def verify_source():
    freeze = HERE / "round22-freeze.json"
    cfg = json.loads(freeze.read_bytes())
    committed = subprocess.check_output(["git", "show", f"HEAD:{freeze.relative_to(r.ROOT).as_posix()}"], cwd=r.ROOT)
    if cfg != json.loads(committed) or cfg["books"] != json.loads(json.dumps(study.books())):
        raise ValueError("changed Round 22 freeze")
    for name, expected in cfg["source"].items():
        if hashlib.sha256((HERE / name).read_text(encoding="utf-8").encode()).hexdigest() != expected:
            raise ValueError(f"changed frozen source: {name}")
    r.verify_freeze()
    dataset = r.DATASETS[r.YEAR]
    manifest = json.loads((dataset / "manifest.json").read_bytes())
    with (dataset / "breeze.sqlite").open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != manifest["files_sha256"]["breeze.sqlite"]:
            raise ValueError("changed frozen market data")


def replay(engine_type, model, days):
    with Y.ROUTER.dispatch():
        engine = engine_type(Y.dataset("year"), model, Y.table("year"), "year")
        engine.trace_days = days
        engine.trace = defaultdict(list)
        data = engine.run(*r.WINDOW)
    for trade in data["trades"]:
        trade.setdefault("status", "CLOSED" if trade.get("net_pnl") is not None else "UNRESOLVED")
    return data, engine.trace


def comparable_metrics(value):
    copy = {**value, "notes": dict(value["notes"])}
    copy["notes"].pop("named_memo_miss", None)
    return copy


def trade_summary(trade):
    fields = ("entry_time", "exit_time", "member", "entry_qty", "entry_premium", "exit_premium",
              "net_pnl", "exit_reason", "tradingsymbol", "direction", "initial_stop_underlying",
              "entry_underlying", "n10_children")
    return {key: trade.get(key) for key in fields}


def prior_trades(raw, trace):
    at = trace[0]["at"]
    visible = [trade for trade in raw["trades"] if trade["status"] == "CLOSED" and trade["exit_time"] <= at]
    return [trade_summary(trade) for trade in sorted(visible, key=lambda trade: trade["exit_time"])[-8:]]


def main(output=None):
    paths = {year: HERE / f"round22-{year}.json" for year in YEARS}
    panels = {year: json.loads(path.read_bytes()) for year, path in paths.items()}
    residuals = day_residuals(panels.values())
    worst = sorted(residuals, key=lambda day: (residuals[day]["native_delta"], day))[:3]
    days = {day for day in worst if day.startswith(r.YEAR)}
    if not days:
        raise ValueError(f"no requested days in {r.YEAR}")
    verify_source()
    r.f.Z.N.B.O27F.deny_network()
    r.f.Z.N.B.L._init()
    accepted, acceptance_trace = replay(AcceptanceTrace, study.books()[study.ACCEPT], days)
    observed = r.metrics(accepted)
    reference = panels[r.YEAR][study.ACCEPT]
    if comparable_metrics(observed) != comparable_metrics(reference):
        raise ValueError(f"acceptance metrics differ: {[key for key in observed if observed[key] != reference[key]]}")
    extras = [trade for trade in accepted["trades"] if trade.get("member") == 5]
    if json.loads(json.dumps(extras, default=str)) != panels[r.YEAR]["extra_trades"][study.ACCEPT]:
        raise ValueError("acceptance sleeve trades differ")
    control, control_trace = replay(ControlTrace, r.books()["N11T"], days)
    _, original_control = study.trades(r.YEAR, "N11T")
    if r.money(control) != r.money(original_control):
        raise ValueError("N11T economic tuples differ")
    report = {
        "window": r.YEAR, "aggregate_native_delta": round(sum(row["native_delta"] for row in residuals.values()), 4),
        "source_reports_sha256": {year: hashlib.sha256(path.read_bytes()).hexdigest() for year, path in paths.items()},
        "reproduction": {"acceptance_daily_cash_and_non_memo_metrics": True, "acceptance_sleeve_rows": True,
                         "n11t_economic_tuples": True},
        "days": {day: {
            **residuals[day],
            "acceptance_trace": acceptance_trace[day], "n11t_trace": control_trace[day],
            "acceptance_prior_closes": prior_trades(accepted, acceptance_trace[day]),
            "n11t_prior_closes": prior_trades(control, control_trace[day]),
            "acceptance_trades": [trade for trade in accepted["trades"] if trade["exit_time"][:10] == day],
            "n11t_trades": [trade for trade in control["trades"] if trade["exit_time"][:10] == day],
        } for day in sorted(days)},
    }
    output = output or HERE / "_local" / f"round22-attribution-{r.YEAR}.json"
    with output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    print(r.YEAR, "reproduced", sorted(days), flush=True)


def compact_decision(trace, at, bar):
    row, = [item for item in trace if item["at"] == at]
    decision, = [item for item in row["planner"] if item["bar_ts"] == bar]
    return {"at": row["at"], "bar": bar, "outcome": decision["outcome"],
            "halts": decision["halts"], "stance": decision["risk_reason"],
            "risk_multiplier": decision["risk_multiplier"], "pool": row["pool"],
            "day_realized": row["realized_day"], "held": row["held"], "filled": row["filled"]}


def combine(output):
    files = [HERE / "_local" / f"round22-attribution-{year}-v2.json" for year in ("2025", "2026")]
    raws = [json.loads(file.read_bytes()) for file in files]
    if any(not all(raw["reproduction"].values()) for raw in raws):
        raise ValueError("incomplete frozen reproduction")
    if len({raw["aggregate_native_delta"] for raw in raws}) != 1 or any(
            raw["source_reports_sha256"] != raws[0]["source_reports_sha256"] for raw in raws):
        raise ValueError("saved traces disagree on reference")
    cases = {day: case for raw in raws for day, case in raw["days"].items()}
    result = {}
    for day in sorted(cases, key=lambda day: cases[day]["native_delta"]):
        case = cases[day]
        checks = []
        for trade in case["n11t_trades"]:
            at, bar = trade["entry_time"], trade["bar_ts"]
            checks.append({
                "n11t": compact_decision(case["n11t_trace"], at, bar),
                "acceptance": compact_decision(case["acceptance_trace"], at, bar),
            })
        native_accepted = [trade for trade in case["acceptance_trades"] if trade["member"] != 5]
        net_delta = sum(trade["net_pnl"] for trade in native_accepted) - sum(
            trade["net_pnl"] for trade in case["n11t_trades"])
        if abs(net_delta - case["native_delta"]) > 0.0001:
            raise ValueError(f"trade cash does not reproduce the daily residual: {day}")
        result[day] = {
            **{key: round(case[key], 4) for key in ("n11t_net", "accept_net", "sleeve_net", "native_delta")},
            "entry_comparisons": checks,
            "n11t_trades": [trade_summary(trade) for trade in case["n11t_trades"]],
            "acceptance_trades": [trade_summary(trade) for trade in case["acceptance_trades"]],
            "acceptance_prior_closes": [{"at": trade["exit_time"], "member": trade["member"], "net": trade["net_pnl"]}
                                       for trade in case["acceptance_prior_closes"]],
        }
    combined = {
        "aggregate_native_delta": raws[0]["aggregate_native_delta"],
        "three_day_native_delta": round(sum(row["native_delta"] for row in result.values()), 4),
        "reproduction": {raw["window"]: raw["reproduction"] for raw in raws},
        "source_reports_sha256": raws[0]["source_reports_sha256"],
        "trace_sha256": {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in files},
        "days": result,
    }
    with output.open("x", encoding="utf-8") as handle:
        json.dump(combined, handle, indent=2, sort_keys=True)
        handle.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--combine", action="store_true")
    args = parser.parse_args()
    if args.combine:
        combine(args.output or HERE / "round22-attribution.json")
    else:
        main(args.output)
