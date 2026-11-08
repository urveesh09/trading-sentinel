"""Check the N11 earned-lot trigger on previously reconciled Production parents."""

import argparse
from collections import defaultdict
from contextlib import closing
from datetime import datetime
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import sqlite3
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3] / "python-engine"))
from fno_n11 import ADD_AT_R, ADD_BAR


def audit(folder: Path) -> dict:
    control = json.loads((HERE / "deployed-control-nov5.json").read_bytes())
    parents = {row["id"]: row for row in control["positions"] if row["lots"] >= 2}
    manifest = json.loads((folder / "manifest.json").read_bytes())
    days = sorted({row["entry"][:10] for row in parents.values()})
    paths = ["fno-replay.sqlite", *(f"fno_exit_paths/{day}.jsonl" for day in days)]
    hashes = {name: sha256((folder / name).read_bytes()).hexdigest() for name in paths}
    if any(digest != manifest["files_sha256"][name] for name, digest in hashes.items()):
        raise ValueError("export hash mismatch")
    marks = defaultdict(list)
    for name in paths[1:]:
        with (folder / name).open(encoding="utf-8") as handle:
            for line in handle:
                mark = json.loads(line)
                if mark["source"] == "FNO_PAPER" and mark["position_id"] in parents:
                    marks[mark["position_id"]].append(mark)

    with closing(sqlite3.connect((folder / paths[0]).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        out = []
        for pos, expected in parents.items():
            row, = db.execute(
                "SELECT * FROM fno_positions WHERE source='FNO_PAPER' AND id=?", (pos,),
            ).fetchall()
            expected_fields = ("entry", "exit", "symbol", "underlying", "lots")
            actual = tuple(row[field] for field in (
                "entry_time", "exit_time", "tradingsymbol", "underlying", "initial_lots",
            ))
            if actual != tuple(expected[field] for field in expected_fields):
                raise ValueError(f"parent identity mismatch: {pos}")
            child_ids = [child[0] for child in db.execute(
                "SELECT id FROM fno_positions WHERE source='FNO_PAPER' AND bar_ts=? ORDER BY id",
                (f"{ADD_BAR}{pos}",),
            )]
            entry, exit_at = (datetime.fromisoformat(row[field]) for field in ("entry_time", "exit_time"))
            risk = abs(row["entry_underlying"] - row["stop_underlying"])
            if risk <= 0 or len(marks[pos]) != expected["held_looks"]:
                raise ValueError(f"parent risk or held path differs: {pos}")
            sign = 1 if row["direction"] == "LONG" else -1
            progress = []
            for mark in marks[pos]:
                if (mark["token"], mark["underlying"]) != (row["token"], row["underlying"]):
                    raise ValueError(f"held instrument mismatch: {pos}")
                at = datetime.fromisoformat(mark["at"])
                future = mark.get("fut")
                if entry < at < exit_at and future is not None and isfinite(future) and future > 0:
                    progress.append((future - row["entry_underlying"]) * sign / risk)
            if not progress:
                raise ValueError(f"no pre-exit futures observations: {pos}")
            out.append({"id": pos, "venue": row["underlying"], "futures_looks_before_exit": len(progress),
                        "max_favorable_r": round(max(progress), 6),
                        "observed_looks_at_or_above_trigger": sum(value >= ADD_AT_R for value in progress),
                        "recorded_child_ids": child_ids})
    return {"export": folder.name, "export_files_sha256": hashes, "trigger_r": ADD_AT_R, "parents": out,
            "scope": "conditional on observed Production parents and recorded pre-exit futures marks"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("export", type=Path)
    print(json.dumps(audit(parser.parse_args().export), indent=2, sort_keys=True))
