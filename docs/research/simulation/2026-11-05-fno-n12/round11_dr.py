"""Evaluate existing regular defined-risk exits on recorded paper structures."""
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from cross_index_coverage import ARCHIVE, digest, read

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LOCAL = HERE / "_local/round11"
DATABASE = ARCHIVE / "fno-replay.sqlite"

import fno_dr_exit_experiment as exp
from intraday_spread_archive_adapter import read_archived_quote_events


def verify():
    path = HERE / "round11-freeze.json"
    spec = read(path)
    assert spec == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{path.relative_to(ROOT).as_posix()}"], cwd=ROOT))
    for file, sha in spec["files"].items():
        assert digest(HERE / file) == sha, file
    assert digest(DATABASE) == spec["position_database_sha256"]
    assert digest(ARCHIVE / "manifest.json") == spec["quote_manifest_sha256"]
    return spec["policy"]


def positions(ledger):
    groups, skipped = defaultdict(list), []
    with sqlite3.connect(DATABASE.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        for raw in db.execute("SELECT * FROM fno_dr_positions WHERE source='FNO_PAPER' ORDER BY id"):
            row = dict(raw)
            ref = f"fno_dr_positions:{row['id']}"
            try:
                opened = datetime.fromisoformat(row["opened_at"]).astimezone(exp.IST).date().isoformat()
                legs = exp._bound_legs_from_row(row)
                if not legs:
                    raise exp.DrStudyError("no_exact_bound_legs")
                if any(leg["contract"]["expiry"] <= opened for leg in legs):
                    raise exp.DrStudyError("outside_regular_scope")
                receipt = ledger.get(f"fno_dr_structure:{row['id']}", {})
                cash = receipt.get("pnl") if receipt.get("count") == 1 else None
                settlement = {"status": row["status"], "settlement_state": row["settlement_state"],
                              "exit_reason": row["exit_reason"], "position_net_pnl": row["pnl"],
                              "ledger_net_pnl": cash}
                entry = exp.verify_entry(exp.entry_envelope(row), settlement)
                groups[opened].append(entry)
            except (exp.DrStudyError, ValueError, TypeError) as exc:
                skipped.append({"position_ref": ref, "reason": str(exc)})
    return groups, skipped


def main():
    policy = verify()
    manifest = read(ARCHIVE / "manifest.json")
    groups, skipped = positions(read(LOCAL / "ledger.json"))
    items = []
    coverage = {}
    for day, entries in sorted(groups.items()):
        for name, sha in manifest["files_sha256"].items():
            if name.startswith(f"quotes/{day}/"):
                assert digest(ARCHIVE / name) == sha, name
        events = read_archived_quote_events(ARCHIVE, days=[day])
        for entry in entries:
            observations, exclusions = exp.observations_from_archive(
                events, entry, max_age_seconds=int(policy["max_gap_seconds"]))
            items.append((entry, observations, exclusions))
            coverage[entry.position_ref] = {
                "date": day, "joint_receipts_after_entry": len(observations),
                "archived_events_on_day": len(events),
            }
    report = exp.build_report(items, policy, unavailable=skipped)
    result = {"report": report, "coverage": coverage}
    with (HERE / "round11-dr-results.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print("positions", len(items) + len(skipped), "bound", len(items),
          "baseline dispositions", dict(Counter(p["reconciliation"]["state"] for p in report["pairs"])),
          "unavailable", dict(Counter(p["reason"] for p in skipped)), flush=True)
    today = [p for p in report["pairs"] if coverage[p["position_ref"]]["date"] == "2026-11-05"]
    for item in today:
        print("November 5", item["baseline"], item["reconciliation"], flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["freeze"]:
        print(json.dumps(exp.freeze_manifest(experiment_id="N012-round11-ordinary-defined-risk")))
    else:
        main()
