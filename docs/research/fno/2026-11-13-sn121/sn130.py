"""SN130 - the scoreboard for SN121-SN129 (PLAN.md), read from the saved result files; nothing is rescored."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def j(n):
    p = HERE / f"results-{n}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


if __name__ == "__main__":
    rows = []
    r = j("sn121")
    if r:
        rows.append(("121", "partner day paths (7 sessions)", r["summary"]))
        rows.append(("121", "partner lock counterfactuals", r["locks"]))
    r = j("sn122")
    if r:
        rows.append(("122", "partner entry drift vs random (p at 1/5/15/30 min)", {h: v["p_value"] for h, v in r["entry"].items()}))
        rows.append(("122", "machine exits on partner entries (per lot)", r["exits_per_lot_same_trips"]))
    r = j("sn123")
    if r:
        rows.append(("123", "partner-like burst scalper, held out vs NULL", {"held_out": r["loyo_real"]["sum"]["net"], "null": r["loyo_null"]["sum"]["net"], "PASS": r["PASS"]}))
        rows.append(("123", "touch table", r["touch"]))
    r = j("sn124")
    if r:
        rows.append(("124", "overnight short fly/condor", r["verdict"]))
    r = j("sn125")
    if r:
        rows.append(("125", "last half-hour (Gold-free)", r["gold-free"]["verdict"]))
    r = j("sn126")
    if r:
        rows.append(("126", "hot-day scalping", {"held_out": r["loyo"]["sum"]["net"], "null": r["loyo_null"]["sum"]["net"], "robust": r["robust"], "PASS": r["PASS"]}))
    r = j("sn128")
    if r:
        rows.append(("128", "morning crush (all days / Gold-free)", {k: r[k]["verdict"] for k in ("all days", "gold-free")}))
    r = j("sn129")
    if r:
        rows.append(("129", "gap-day sleeve", {"formed": r["formed"], "sleeve": r["sleeve"], "vs_gold": r["vs_gold"]}))
    for sn, what, val in rows:
        print(f"SN{sn} | {what:55s} | {json.dumps(val, default=str)[:400]}")
    (HERE / "results-sn130.json").write_text(json.dumps([{"SN": a, "what": b, "result": c} for a, b, c in rows], indent=1, default=str),
                                             encoding="utf-8")
