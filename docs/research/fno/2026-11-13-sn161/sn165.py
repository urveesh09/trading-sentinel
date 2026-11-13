"""SN165 - the capital ladder (PLAN.md). Development sessions. Wallets Rs 15k / 30k / 50k / 1 lakh; wage a fixed
Rs 1,500 or 10% of the wallet; stop per trade = the wage; day limit = 2 x the wage; one attempt. Lots: one per Rs 15k
of wallet (Gold's convention) or as many as the wallet buys. Shapes ATM and 2 strikes OTM; random entries (20
replays) and the 15-minute range break."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pw  # noqa: E402

DRAWS = 20


def run(ss, picker_for, wallet, wage, max_lots):
    out = {}
    for S in ss:
        net, trades = pw.play(S, picker_for(S), wallet, wage, wage, 1, day_limit=2 * wage, max_lots=max_lots)
        if trades:
            out[S.day] = net
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn165.json"
    if out_path.exists():
        raise SystemExit("SN165 is scored once")
    ss = pw.dev_sessions()
    days = [S.day for S in ss]
    res = {}
    for wallet, wage_mode, lots_mode, off in itertools.product((15000.0, 30000.0, 50000.0, 100000.0), ("fixed 1500", "10%"),
                                                               ("1 per 15k", "max"), (0, 2)):
        wage = 1500.0 if wage_mode == "fixed 1500" else 0.10 * wallet
        max_lots = max(1, int(wallet // 15000)) if lots_mode == "1 per 15k" else None
        rnd = [pw.wage_stats(run(ss, lambda S, k=k: pw.random_picker(pw.seed_of(S.day, k), off), wallet, wage, max_lots),
                             days, wallet, wage) for k in range(DRAWS)]
        mom = pw.wage_stats(run(ss, lambda S: pw.range_break_picker(15, off), wallet, wage, max_lots), days, wallet, wage)
        key = f"Rs {wallet:,.0f} | wage {wage_mode} ({wage:,.0f}) | lots {lots_mode} | {'ATM' if not off else 'OTM 2'}"
        res[key] = {"random": {"wage_share": round(float(np.mean([s["wage_share"] for s in rnd])), 4),
                               "net_mean": round(float(np.mean([s["net"] for s in rnd]))),
                               "net_pct_of_wallet": round(float(np.mean([s["net"] for s in rnd])) / wallet * 100, 1)},
                    "range break": {"wage_share": mom["wage_share"], "net": mom["net"],
                                    "net_pct_of_wallet": round(mom["net"] / wallet * 100, 1),
                                    "by_year": {y: v["net"] for y, v in mom["by_year"].items()}}}
        print(f"SN165 {key}: {json.dumps(res[key])}", flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
