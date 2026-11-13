"""SN183 - expiry days in the calendar (PLAN.md). The lab's 742 sessions leave out NIFTY expiry days (about one a
week). The expiry-day research (E-series, NIFTY 2024 and 2025 expiry days, in-sample) stored per-arm totals - net,
trades, wins, losing days, worst - but not day-by-day results, so wage days on expiry days cannot be counted from them.
This reads what is stored for E02 / E03 / E03.1 (the 13:00-15:00 'late' slice, ordinary fills) and reports net per
expiry day and the share of winning expiry days, beside the lab calendar's share of expiry days."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pw  # noqa: E402

SRC = pw.C.M.ROOT / "docs" / "research" / "simulation" / "2026-11-03-expiry-e032" / "late-results.json"

if __name__ == "__main__":
    out_path = HERE / "results-sn183.json"
    if out_path.exists():
        raise SystemExit("SN183 is scored once")
    d = json.loads(SRC.read_text(encoding="utf-8"))
    res = {"source": str(SRC.relative_to(pw.C.M.ROOT)).replace("\\", "/"), "arms": {}}
    for arm in ("L_E02", "L_E03", "L_E031"):
        for yr in ("2024", "2025", "both"):
            a = d["arms"].get(f"{arm}|{yr}|ordinary")
            if not a:
                continue
            t = int(float(a["trades"]))
            res["arms"][f"{arm} {yr}"] = {"net": round(float(a["net"])), "trades": t, "wins": int(float(a["wins"])),
                                          "loss_days": int(float(a["loss_days"])), "worst": round(float(a["worst"])),
                                          "net_per_trade": round(float(a["net"]) / t, 1) if t else None}
    res["expiry_days_per_year_note"] = "NIFTY weekly expiry: ~52 days a year (Thursday until Aug 2025, Tuesday since Sep 2025)"
    print("SN183", json.dumps(res), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
