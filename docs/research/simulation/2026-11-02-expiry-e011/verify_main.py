"""expiry-v4: did the swap do only what it says? The real tick, the real store, every archived session, ordinary and adverse.

Compared with the engine as it stood before the swap (commit 3c23adf, the stored NATIVE_E011 runs):

  * The new C must equal the old CE011, field by field and event by event: the main ticket now runs the rule that was tested.
  * The new CL must equal the old C: the old rule is kept, exactly, on the same ticket.
  * Every other play must be unchanged, including CE01 and CE011R, and the number of quote requests must not move.

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

R.LOCAL = HERE / "_local"
FIELDS = ("symbol", "token", "lot_size", "lots", "lots_open", "entry_ts", "entry_price", "max_loss", "peak", "stop", "banked", "exit_pending",
          "status", "gross", "costs", "net_pnl", "assumed_pnl", "bank_pending", "side", "width", "execution", "fee_snapshot")
LINKS = ("e01_version", "e011_version", "paired_primary_id")
# new play -> the old play it must equal
RENAMED = {"C": "CE011", "CL": "C"}
SAME = ("A", "B", "AL", "BH", "BL", "BR", "C500", "CH", "CI", "D", "CE01", "CE011R")


def legs(positions, play):
    return {(p["symbol"], p["entry_ts"]): p for p in positions if p["play"] == play}


def strip(rows):
    return [{a: b for a, b in e.items() if a not in LINKS} for e in rows]


async def main(label: str) -> int:
    R.disable_network()
    checks, bad = [], []
    for adverse in (False, True):
        for day, u in R.sessions():
            suffix = "adverse" if adverse else "ordinary"
            stored = json.loads((R.LOCAL / "evals" / f"{day}-{u}-NATIVE_E011-{suffix}.json").read_text())
            result = await R.run_one(day, u, policy=label, adverse=adverse)
            count = 0
            for new_play, old_play in [*RENAMED.items(), *((p, p) for p in SAME)]:
                old, new = legs(stored["positions"], old_play), legs(result["positions"], new_play)
                if old.keys() != new.keys():
                    bad.append((day, suffix, new_play, old_play, "legs differ", sorted(old.keys() ^ new.keys())))
                for k in old.keys() & new.keys():
                    count += 1
                    for f in FIELDS:
                        if old[k][f] != new[k][f]:
                            bad.append((day, suffix, new_play, old_play, k, f, old[k][f], new[k][f]))
                    if strip(old[k]["events"]) != strip(new[k]["events"]):
                        bad.append((day, suffix, new_play, old_play, k, "events"))
            if [p for p in result["positions"] if p["play"] == "CE011"]:
                bad.append((day, suffix, "CE011 still trades"))
            if result["provider_calls"] != stored["provider_calls"]:
                bad.append((day, suffix, "quote requests moved", result["provider_calls"], stored["provider_calls"]))
            parents = {p["id"]: p for p in result["positions"] if p["play"] == "C"}
            for p in result["positions"]:
                if p["play"] in ("CL", "CE01", "CE011R"):
                    twin = parents.get(p["events"][0].get("paired_primary_id"))
                    if twin is None or (twin["symbol"], twin["entry_ts"], twin["lots"], twin["entry_price"], twin["max_loss"]) != \
                            (p["symbol"], p["entry_ts"], p["lots"], p["entry_price"], p["max_loss"]) or p["max_loss"] > 2500:
                        bad.append((day, suffix, p["play"], "not C's ticket"))
            checks.append(dict(day=day, underlying=u, adverse=adverse, legs_compared=count))
    print("cases", len(checks), "legs compared", sum(c["legs_compared"] for c in checks), "mismatches", len(bad), flush=True)
    for row in bad[:20]:
        print("  ", row)
    (HERE / f"native-parity-{label}.json").write_text(json.dumps(dict(
        passed=not bad, cases=checks, mismatches=len(bad),
        compared_with="the engine before the swap, commit 3c23adf (NATIVE_E011): new C = old CE011, new CL = old C, all others unchanged"), indent=1) + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "NATIVE_V4")))
