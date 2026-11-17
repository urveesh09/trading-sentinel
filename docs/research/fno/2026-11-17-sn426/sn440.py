"""SN440 (own): Gold's real cost per lot - Production's paper fills against the replay's model (PLAN.md section 2, frozen
at 123301ac; details fixed here before any number). Read only.

Fills: fno_positions in Production's sealed export (FNO_PAPER, NIFTY, CLOSED, entry Jul 16 - Oct 28, 2026: the dates gl
holds). The paper engine fills at the live quote (ask in, bid out) at its entry_time / exit_time.
Model: gl's session for the entry day (front weekly only: the position's expiry must be gl's front, else skipped and
counted); the option's Breeze minute close at the fill's minute (if the fill second >= 30) or the minute before (if < 30),
then wk.ask on entry and wk.bid on exit - the prices Gold's replay charges before its stress.
Per position and lot: extra = (paper entry - model ask) x lot + (model bid - paper exit) x lot (positive = real dearer
than the model); also the paper prices against the Breeze close (the half-spread actually paid each way).
Reported: n, mean, median, p75 / p90 of the extra per lot, by entry hour and moneyness, against Rs 205 / 400.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-17-sn396"))
import op  # noqa: E402

gl, wk = op.gl, op.wk
OUT = HERE / "results-sn440.json"
EXPORT = Path(r"C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel"
              r"\_local\exports\20261116T103002Z")


def ts(s):
    d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d.astimezone(dt.timezone(dt.timedelta(hours=5, minutes=30)))


def model_close(s, k, o, t):
    m = t.hour * 60 + t.minute - 555
    i = m if t.second >= 30 else m - 1
    return gl.opx(s, k, o, i, look=2), i


def main():
    if OUT.exists():
        raise SystemExit("SN440 is run once")
    man = json.loads((EXPORT / "manifest.json").read_text(encoding="utf-8"))
    dbp = EXPORT / "fno-replay.sqlite"
    want = (man.get("files_sha256") or {}).get("fno-replay.sqlite")
    if want:
        assert hashlib.sha256(dbp.read_bytes()).hexdigest() == want
    con = sqlite3.connect(f"file:{dbp.as_posix()}?mode=ro", uri=True)
    rows = con.execute("SELECT tradingsymbol, expiry, strike, opt_type, lots, lot_size, entry_time, entry_premium, exit_time, exit_premium, strategy, entry_underlying "
                       "FROM fno_positions WHERE source='FNO_PAPER' AND underlying='NIFTY' AND status='CLOSED'").fetchall()
    smp, _days, _au = op.setup()
    out, skipped = [], {"no_gl_session": 0, "not_front_expiry": 0, "no_model_price": 0}
    for sym, exp, k, o, lots, lot, et, ep, xt, xp, strat, eu in rows:
        te, tx = ts(et), ts(xt)
        d = te.date().isoformat()
        if d not in smp.s or tx.date() != te.date():
            skipped["no_gl_session"] += 1
            continue
        s = smp.s[d]
        if s["expiry"] != str(exp)[:10]:
            skipped["not_front_expiry"] += 1
            continue
        k = int(round(float(k)))
        ce, ie = model_close(s, k, o, te)
        cx, ix = model_close(s, k, o, tx)
        if ce is None or cx is None:
            skipped["no_model_price"] += 1
            continue
        ma, mb = wk.ask(smp.mk, ce), wk.bid(smp.mk, cx)
        lot = int(lot or 65)
        spot = s["index"][3][max(0, ie)]
        mny = (k - spot) * (1 if o == "PE" else -1)
        out.append({"day": d, "strategy": strat, "hour": te.hour, "moneyness_pts": round(float(mny), 1),
                    "entry_paper": ep, "entry_model_ask": ma, "entry_close": ce, "exit_paper": xp, "exit_model_bid": mb, "exit_close": cx,
                    "extra_per_lot": round((ep - ma) * lot + (mb - xp) * lot, 2),
                    "paper_half_spreads_per_lot": round((ep - ce) * lot + (cx - xp) * lot, 2),
                    "model_half_spreads_per_lot": round((ma - ce) * lot + (cx - mb) * lot, 2)})
    xs = np.array([r["extra_per_lot"] for r in out]) if out else np.array([])
    res = {"positions": len(rows), "compared": len(out), "skipped": skipped}
    if len(xs):
        res.update(extra_per_lot={"mean": round(float(xs.mean()), 1), "median": round(float(np.median(xs)), 1), "p75": round(float(np.percentile(xs, 75)), 1),
                                  "p90": round(float(np.percentile(xs, 90)), 1), "share_above_205": round(float((xs > 205).mean()), 3), "share_above_400": round(float((xs > 400).mean()), 3)},
                   paper_half_spreads_per_lot_median=round(float(np.median([r["paper_half_spreads_per_lot"] for r in out])), 1),
                   model_half_spreads_per_lot_median=round(float(np.median([r["model_half_spreads_per_lot"] for r in out])), 1),
                   by_hour={h: round(float(np.mean([r["extra_per_lot"] for r in out if r["hour"] == h])), 1) for h in sorted({r["hour"] for r in out})},
                   by_strategy={s_: {"n": sum(1 for r in out if r["strategy"] == s_), "mean": round(float(np.mean([r["extra_per_lot"] for r in out if r["strategy"] == s_])), 1)}
                                for s_ in sorted({r["strategy"] or "?" for r in out})})
    res["rows"] = out
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, default=float))


if __name__ == "__main__":
    main()
