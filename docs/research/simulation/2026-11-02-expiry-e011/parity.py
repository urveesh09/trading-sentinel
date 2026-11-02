"""Is the fast lab the engine? Every leg of A, B, C and CE01 on all eight sessions, ordinary and adverse.

Compared with the native replay's stored results (`NATIVE_E01_FINAL`), field by field and event by event.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import e011_lab as L

EVALS = L.ROOT / "docs/research/simulation/2026-11-02-expiry-e01/_local/evals"
FIELDS = ("lots", "entry_price", "peak", "stop", "banked", "status", "gross", "costs", "net_pnl", "assumed_pnl", "max_loss", "lots_open")


def stored(day, u, adverse):
    p = EVALS / f"{day}-{u}-NATIVE_E01_FINAL-{'adverse' if adverse else 'ordinary'}.json"
    return json.loads(p.read_text())


def key(p):
    return (p["play"], p["symbol"], p["entry_ts"])


def events(rows):
    return [(e["ts"], e["action"], e.get("lots"), e.get("price"), e.get("gross"), e.get("charges"), e.get("net")) for e in rows
            if e["action"] not in ("SETTLED_ASSUMED", "UNRESOLVED")]


def compare(day, u, adverse):
    S = L.Recorded(day, u, adverse)
    native = {key(p): p for p in stored(day, u, adverse)["positions"] if p["play"] in ("A", "B", "C", "CE01")}
    mine = {}
    for p in L.run_a(S) + L.run_b(S) + L.run_c(S, L.C_NATIVE, "C") + L.run_c(S, L.E01, "CE01"):
        mine[key(p)] = p
    # The same rules under a play name the engine has never heard of: a candidate must behave like its rules,
    # not like its name. This check exists because the first genome ran under name X with no stop at all.
    for p in L.run_c(S, L.E01, "X"):
        twin = mine[("CE01", p["symbol"], p["entry_ts"])]
        for f in FIELDS:
            if p[f] != twin[f]:
                native["__renamed__"] = p
                mine["__renamed__"] = p
    bad = []
    for k in native.keys() | mine.keys():
        a, b = native.get(k), mine.get(k)
        if a is None or b is None:
            bad.append((k, "missing", a is None, b is None))
            continue
        for f in FIELDS:
            if a[f] != b[f]:
                bad.append((k, f, a[f], b[f]))
        if events(a["events"]) != events(b["_events"]):
            bad.append((k, "events", events(a["events"]), events(b["_events"])))
    return len(native), bad


def main() -> int:
    total, problems = 0, 0
    for adverse in (False, True):
        for day, u in L.recorded_keys():
            count, bad = compare(day, u, adverse)
            total += count
            problems += len(bad)
            print(day, u, "adverse" if adverse else "ordinary", "legs", count, "mismatches", len(bad), flush=True)
            for row in bad[:6]:
                print("   ", row)
    print("TOTAL legs", total, "mismatches", problems)
    (Path(__file__).parent / "parity.json").write_text(json.dumps({"legs": total, "mismatches": problems}, indent=1) + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
