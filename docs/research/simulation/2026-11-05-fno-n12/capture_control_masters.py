"""Emit the scoped dated contract identities needed by the control audit."""

import hashlib
import json
from pathlib import Path


FIRST, LAST = "2026-09-10", "2026-10-28"


def nearest(contracts, day, allowed):
    return min(row["expiry"] for row in contracts
               if row["instrument_type"] in allowed and row["expiry"] >= day)


def collect(root):
    result = {}
    for venue, name in (("NFO", "NIFTY"), ("BFO", "SENSEX")):
        days = {}
        for manifest in sorted((root / venue).glob("*/*/manifest.json")):
            day = manifest.parent.parent.name
            if not FIRST <= day <= LAST:
                continue
            if day in days:
                raise ValueError(f"Ambiguous master observation for {venue} {day}")
            raw = manifest.read_bytes()
            spec = json.loads(raw)
            canonical = (manifest.parent / "contracts.jsonl").read_bytes()
            raw_contracts = (manifest.parent / "raw.csv").read_bytes()
            if (spec["segment"] != venue or hashlib.sha256(canonical).hexdigest() != spec["canonical_sha256"] or
                    hashlib.sha256(raw_contracts).hexdigest() != spec["raw_sha256"]):
                raise ValueError(f"Changed master archive for {venue} {day}")
            all_rows = [json.loads(line) for line in canonical.splitlines()]
            if len(all_rows) != spec["contract_count"]:
                raise ValueError(f"Incomplete master for {venue} {day}")
            rows = [row for row in all_rows if row["underlying"] == name]
            weekly = nearest(rows, day, {"CE", "PE"})
            monthly = nearest(rows, day, {"FUT"})
            chosen = [row for row in rows if
                      (row["instrument_type"] == "FUT" and row["expiry"] == monthly) or
                      (row["instrument_type"] in {"CE", "PE"} and row["expiry"] == weekly)]
            fields = ("tradingsymbol", "expiry", "strike", "instrument_type", "lot_size", "tick_size")
            contracts = {row["instrument_token"]: [row[field] for field in fields] for row in chosen}
            if len(contracts) != len(chosen):
                raise ValueError(f"Conflicting master tokens for {venue} {day}")
            days[day] = {"observed_at": spec["observed_at_utc"], "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                         "option_expiry": weekly, "front_expiry": monthly, "contracts": contracts}
        result[name] = days
    return result


if __name__ == "__main__":
    print(json.dumps(collect(Path("/data/research/contract-masters/KITE")), sort_keys=True))
