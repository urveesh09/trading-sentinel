"""SN450: the Gold-plus-candidate chronological test (PLAN.md section 1, frozen at f56f5807; details fixed here before any
number). No candidate of this round survived its own bar, so the companion ledger is NOT_TRIGGERED; the Gold-only baseline
every future candidate must beat is computed now, on ALL market sessions.

Gold v5 (DEPLOYED, Rs 30k, growth as deployed), paths 2022 and 2023-26 (to Oct 28, 2026), Rs 205 / 400. Market sessions =
every NIFTY session with a 15:29 index bar in the history database (Breeze, read only); a session Gold's replay does not
hold (expiry, special, data hole) counts as Rs 0.
  all-session net and per all-session; net without the 5 best dates
  payout months (net > 0) of all months
  Rs 750 days: sessions with net >= Rs 750 (count, share of all sessions)
  dry spells: the longest run of sessions without a new high of cumulative net, and the longest run of sessions with net <= 0
  refills (sum of losing days); the worst day; final wallet
Protocol for a future candidate (frozen here): Gold has priority on the one position; the candidate trades only while Gold is
flat, its loss reduces Gold's day room (SN252's leg contract), and a Gold signal forces it out; it is charged for cash locked
in its exits, the reserved loss room, fee floors, changed growth steps and every Gold trade it blocks. It is judged on the
same measures at both stresses, and it must beat Gold-only on all-session net AND net without the best 5 dates AND not lengthen
the longest dry spell, in the unseen period it is frozen for.
"""
from __future__ import annotations

import collections
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-17-sn411"))
import gold  # noqa: E402

OUT = HERE / "results-sn450.json"
DB = "file:C:/Users/Urveesh/sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite?mode=ro"


def sessions():
    c = sqlite3.connect(DB, uri=True)
    return sorted({r[0][:10] for r in c.execute("SELECT datetime FROM candles WHERE kind='index' AND underlying='NIFTY' AND expiry='' AND strike=0 AND opt='' "
                                                "AND interval='1minute' AND datetime>='2022-01-01' AND datetime<'2026-10-29' AND datetime LIKE '% 15:29:00'")})


def metrics(days, cal):
    net = {d: n for d, _w, n, _t, _l in days}
    xs = [net.get(d, 0.0) for d in cal]
    tot = sum(xs)
    by_m = collections.defaultdict(float)
    for d, x in zip(cal, xs):
        by_m[d[:7]] += x
    cum, hi, run, best_run, run0, best_run0 = 0.0, 0.0, 0, 0, 0, 0
    for x in xs:
        cum += x
        if cum > hi + 1e-9:
            hi, run = cum, 0
        else:
            run += 1
            best_run = max(best_run, run)
        run0 = run0 + 1 if x <= 0 else 0
        best_run0 = max(best_run0, run0)
    top5 = sorted(xs, reverse=True)[:5]
    return {"market_sessions": len(cal), "gold_replay_sessions": len(net), "net": round(tot), "per_market_session": round(tot / len(cal), 1),
            "net_without_best5": round(tot - sum(top5)), "best5": [round(x) for x in top5],
            "payout_months": sum(v > 0 for v in by_m.values()), "months": len(by_m),
            "days_ge_750": sum(x >= 750 for x in xs), "share_days_ge_750": round(sum(x >= 750 for x in xs) / len(cal), 3),
            "trading_days": sum(x != 0 for x in xs), "longest_no_new_high_sessions": best_run, "longest_nonpositive_run_sessions": best_run0,
            "refilled": round(sum(-x for x in xs if x < 0)), "worst_day": round(min(xs)), "final_wallet": round(days[-1][1]) if days else None}


def main():
    if OUT.exists():
        raise SystemExit("SN450 is run once")
    cal = sessions()
    res = {"candidate_ledger": "NOT_TRIGGERED (no survivor this round)"}
    for p, years in (("2022", gold.Y22), ("2023-2026", gold.Y2326)):
        cp = [d for d in cal if d[:4] in years]
        for st in (205.0, 400.0):
            days, log, _ = gold.run(years, gold.DEPLOYED, st)
            extra = sorted({d for d, *_r in days} - set(cp))          # a Gold session without a 15:29 index bar still counts
            res[f"GOLD-ONLY | {p} @{int(st)}"] = metrics(days, sorted(set(cp) | set(extra)))
            res[f"GOLD-ONLY | {p} @{int(st)}"]["gold_sessions_missing_from_calendar"] = extra
            print(p, int(st), json.dumps(res[f"GOLD-ONLY | {p} @{int(st)}"]), flush=True)
    assert res["GOLD-ONLY | 2023-2026 @205"]["net"] in (850882, 850883)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
