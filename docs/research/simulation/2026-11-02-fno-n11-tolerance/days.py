"""Worst days and lost trades for a tolerance book against N11. From saved replays only. A development view."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-02-fno-n11"))
import screen_view as V  # noqa: E402

V.LOCAL = HERE / "_local"
YEARS = V.YEARS


def main(phase: str, base: str, name: str) -> None:
    rows = [t for y in YEARS for t in V.load(V.LOCAL, phase, y, name)["trades"]]
    days = defaultdict(float)
    for t in rows:
        days[t["exit_time"][:10]] += float(t["net_pnl"])
    worst = sorted(days.items(), key=lambda kv: kv[1])[:5]
    print("worst days", [(d, round(v)) for d, v in worst])
    for d, _v in worst[:3]:
        for t in sorted(rows, key=lambda r: r["entry_time"]):
            if t["exit_time"][:10] == d:
                i = t.get("n11_entry") or {}
                print("  ", t["entry_time"][:16], "member", t["member"], t["direction"][0], "lots", t["entry_qty"] // 65, "prem", t["entry_premium"], "->", t["exit_premium"], t["exit_reason"][:13], round(t["net_pnl"]), "raised" if i.get("raised_from") else "", "vol" if i.get("vol_up") else "lowvol", "ev+" if i.get("evidence") else "ev-")
    a = {(t["entry_time"], t["tradingsymbol"]): t for y in YEARS for t in V.load(V.LOCAL, phase, y, base)["trades"]}
    b = {(t["entry_time"], t["tradingsymbol"]): t for t in rows}
    print("in N11, not here:")
    for k, t in sorted(a.items()):
        if k not in b:
            print("  ", k[0][:16], "member", t["member"], t["direction"][0], "lots", t["entry_qty"] // 65, "prem", t["entry_premium"], t["exit_reason"][:13], round(t["net_pnl"]))
    print("here, not in N11:")
    for k, t in sorted(b.items()):
        if k not in a:
            print("  ", k[0][:16], "member", t["member"], t["direction"][0], "lots", t["entry_qty"] // 65, "prem", t["entry_premium"], t["exit_reason"][:13], round(t["net_pnl"]))


if __name__ == "__main__":
    main(*sys.argv[1:4])
