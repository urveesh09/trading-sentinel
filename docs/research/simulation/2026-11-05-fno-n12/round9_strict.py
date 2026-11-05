"""Apply the predeclared strict tape and chain conditions to the calendar arm."""
import copy
from dataclasses import replace
from datetime import date
import json
import os
import subprocess

import round9 as run
from config import settings

BASE = run.Replay


class StrictReplay(BASE):
    def _entry(self, book, obs, frame, day, now):
        if obs.future.contract.name == "SENSEX":
            step = 100
            atm = round(obs.future.ltp / step) * step
            limit = step * int(settings.FNO_STRIKE_WINDOW)
            nearby = {token: q for token, q in obs.options.items() if abs(q.contract.strike - atm) <= limit}
            obs = replace(obs, options=nearby)
        return super()._entry(book, obs, frame, day, now)


def verify():
    path = run.HERE / "round9-strict-freeze.json"
    frozen = json.loads(path.read_bytes())
    assert frozen == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{path.relative_to(run.r.ROOT).as_posix()}"], cwd=run.r.ROOT))
    for file, sha in frozen["files"].items():
        assert run.digest(run.HERE / file) == sha, file
    run.verify()


def main():
    verify()
    year = run.r.YEAR
    stress = os.environ.get("N12_STRESS") == "1"
    tag = "stress" if stress else "base"
    run.r.f.Z.N.B.L._init()
    nifty = run.Y.dataset("year")
    sensex = run.SensexData(stress)
    coverage = sensex.manifest["coverage"]
    allow = {d for d, v in coverage.items() if d.startswith(year)
             and v["status"] == "OBSERVED" and not v["future_missing"]}
    calendar, _ = nifty.option_expiries()
    assert all(date.fromisoformat(d) in calendar for d in allow)
    original = json.loads((run.LOCAL / f"results-{year}-{tag}.json").read_bytes())
    controls = {k: original[k] for k in ("N11", "N11T")}
    for name, result in controls.items():
        if not stress:
            _, expected = run.trades(year, name)
            assert run.r.money(result) == run.r.money(expected)
    candidate = copy.deepcopy(run.r.books()["N11T"])
    candidate["label"] = f"N12|CALENDAR_STRICT|{tag}"
    if stress:
        candidate["cost"] = [400.0, 10.0]
    data = run.SharedDays(nifty, sensex, allow)
    run.Replay = StrictReplay
    result = run.evaluate(candidate, data)
    run.Replay = BASE
    rows = [t for t in result["trades"] if t["tradingsymbol"].startswith("SENSEX")]
    for row in rows:
        if row["status"] != "CLOSED":
            continue
        assert row["entry_time"][:10] in allow
        assert row["entry_qty"] == 20 and not row.get("n10_children")
        gross = (row["exit_premium"] - row["entry_premium"]) * 20
        fees = run.FEES(row["entry_premium"], row["exit_premium"], 20, "BFO")
        assert abs(gross - fees - row["extra_cost"] - row["net_pnl"]) < .02
    with (run.LOCAL / f"strict-results-{year}-{tag}.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, default=str)
    summary = {k: run.r.metrics(v) for k, v in {**controls, "CALENDAR_STRICT": result}.items()}
    summary["selected_days"] = sorted(data.selected)
    summary["sensex_trades"] = rows
    with (run.HERE / f"round9-strict-{year}-{tag}.json").open("x", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    print(year, tag, "selected", len(data.selected), "BFO", len(rows),
          "shared net", summary["CALENDAR_STRICT"]["net"], "unresolved", summary["CALENDAR_STRICT"]["unresolved"], flush=True)


if __name__ == "__main__":
    main()
