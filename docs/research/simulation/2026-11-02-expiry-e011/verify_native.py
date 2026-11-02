"""Does the engine do what was tested? The real tick, the real store, every archived session, ordinary and adverse.

  * A, B, C and CE01 must equal E01's stored native results exactly: E01.1 changes nothing that exists.
  * CE011 and CE011R must equal the lab's frozen E011 and E011R, field by field and event by event.
  * The number of quote requests must not change: the shadows hold C's contract.

Offline, no network, no orders. Each run takes a new label so earlier receipts are never overwritten.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
E01 = ROOT / "docs/research/simulation/2026-11-02-expiry-e01"
sys.path[:0] = [str(HERE), str(E01)]

import replay as R  # noqa: E402

import arms as M  # noqa: E402
import e011_lab as L  # noqa: E402

R.LOCAL = L.LOCAL
FIELDS = ("lots", "entry_ts", "entry_price", "peak", "stop", "banked", "status", "gross", "costs", "net_pnl", "assumed_pnl", "max_loss",
          "lots_open", "bank_pending", "exit_pending", "symbol", "lot_size", "fee_snapshot", "execution")
OLD_FIELDS = ("symbol", "token", "lot_size", "lots", "lots_open", "entry_ts", "entry_price", "max_loss", "peak", "stop", "banked", "exit_pending",
              "status", "gross", "costs", "net_pnl", "assumed_pnl", "bank_pending", "side", "width", "execution", "fee_snapshot")


def key(p):
    return p["play"], p["symbol"], p["entry_ts"]


def events(rows):
    return [(e["ts"], e["action"], e.get("lots"), e.get("price"), e.get("gross"), e.get("charges"), e.get("net")) for e in rows
            if e["action"] not in ("SETTLED_ASSUMED", "UNRESOLVED")]


async def main(label: str) -> int:
    R.disable_network()
    checks, bad = [], []
    stored_dir = E01 / "_local/evals"
    for adverse in (False, True):
        for day, u in R.sessions():
            suffix = "adverse" if adverse else "ordinary"
            result = await R.run_one(day, u, policy=label, adverse=adverse)
            stored = json.loads((stored_dir / f"{day}-{u}-NATIVE_E01_FINAL-{suffix}.json").read_text())

            # Nothing that existed may move.
            plays = ("A", "B", "C", "CE01")
            old = {key(p): p for p in stored["positions"] if p["play"] in plays}
            new = {key(p): p for p in result["positions"] if p["play"] in plays}
            if old.keys() != new.keys():
                bad.append((day, suffix, "existing legs differ", sorted(old.keys() ^ new.keys())))
            for k in old.keys() & new.keys():
                for f in OLD_FIELDS:
                    if old[k][f] != new[k][f]:
                        bad.append((day, suffix, k, f, old[k][f], new[k][f]))
                strip = lambda rows: [{a: b for a, b in e.items() if a not in ("e01_version", "paired_primary_id")} for e in rows]
                if strip(old[k]["events"]) != strip(new[k]["events"]):
                    bad.append((day, suffix, k, "events"))
            if result["provider_calls"] != stored["provider_calls"]:
                bad.append((day, suffix, "extra quote request", result["provider_calls"], stored["provider_calls"]))

            # The shadows must be the frozen arms.
            S = L.Recorded(day, u, adverse)
            parents = {p["id"]: p for p in result["positions"] if p["play"] == "C"}
            count = 0
            for play, arm in (("CE011", "E011"), ("CE011R", "E011R")):
                lab = {p["entry_ts"]: p for p in L.run_c(S, M.ARMS[arm], play)}
                native = {p["entry_ts"]: p for p in result["positions"] if p["play"] == play}
                if lab.keys() != native.keys():
                    bad.append((day, suffix, play, "entries", sorted(lab), sorted(native)))
                for ts in lab.keys() & native.keys():
                    a, b = lab[ts], native[ts]
                    count += 1
                    for f in FIELDS:
                        if a[f] != b[f]:
                            bad.append((day, suffix, play, f, a[f], b[f]))
                    if events(a["_events"]) != events(b["events"]):
                        bad.append((day, suffix, play, "events", events(a["_events"]), events(b["events"])))
                    twin = parents[b["events"][0]["paired_primary_id"]]
                    if (twin["symbol"], twin["entry_ts"], twin["lots"], twin["entry_price"], twin["max_loss"]) != \
                            (b["symbol"], b["entry_ts"], b["lots"], b["entry_price"], b["max_loss"]) or b["max_loss"] > 2500:
                        bad.append((day, suffix, play, "not C's ticket"))
            checks.append(dict(day=day, underlying=u, adverse=adverse, shadow_legs=count))
    print("cases", len(checks), "shadow legs", sum(c["shadow_legs"] for c in checks), "mismatches", len(bad), flush=True)
    for row in bad[:20]:
        print("  ", row)
    (HERE / f"native-parity-{label}.json").write_text(json.dumps(dict(passed=not bad, cases=checks, mismatches=len(bad), compared_with="E01 NATIVE_E01_FINAL and the frozen lab"), indent=1) + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "NATIVE_E011")))
