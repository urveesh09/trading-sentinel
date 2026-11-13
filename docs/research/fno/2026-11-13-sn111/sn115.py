"""SN115 - what latency really costs (measurement; PLAN.md). Production's paper NIFTY entries inside the 40 sealed
quote days (fno-replay.sqlite, hash-checked against the export manifest): delay from the signal bar's close to the
fill, the fill against the archived mid when the signal was decided, the move after the fill; the same post-entry
measures for scheduled 10:00 ATM buys as a control. Rupees per lot of 65."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pb  # noqa: E402

qa = pb.qa
DB = qa.EXPORT / "fno-replay.sqlite"


def minute_of(t: dt.datetime):
    return t.hour * 60 + t.minute - 555


def mid(r, i):
    if i is None or not (0 <= i < qa.NM) or not r["usable"][i] or np.isnan(r["bid"][i]) or np.isnan(r["ask"][i]):
        return None
    return (r["bid"][i] + r["ask"][i]) / 2


def stats(xs):
    xs = [x for x in xs if x is not None]
    return {"n": len(xs), "mean": round(float(np.mean(xs)), 1) if xs else None, "median": round(float(np.median(xs)), 1) if xs else None}


if __name__ == "__main__":
    out_path = HERE / "results-sn115.json"
    if out_path.exists():
        raise SystemExit("SN115 is scored once")
    assert hashlib.sha256(DB.read_bytes()).hexdigest() == qa.manifest()["files_sha256"]["fno-replay.sqlite"]
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    cols = [r[1] for r in con.execute("PRAGMA table_info(fno_positions)")]
    pos = [dict(zip(cols, r)) for r in con.execute("SELECT * FROM fno_positions WHERE source='FNO_PAPER' AND underlying='NIFTY'")]
    qdays = set(qa.days())
    rows = []
    for p in pos:
        if p["entry_date"] not in qdays:
            continue
        q = qa.load(p["entry_date"])
        r = q["opt"].get(("NIFTY", p["expiry"], int(round(p["strike"])), p["opt_type"]))
        et = dt.datetime.fromisoformat(p["entry_time"]).replace(tzinfo=None)
        bar = dt.datetime.fromisoformat(p["bar_ts"])
        close = bar + dt.timedelta(minutes=5)
        lot = p["lot_size"]
        row = {"day": p["entry_date"], "strike": p["strike"], "opt": p["opt_type"], "delay_s": (et - close).total_seconds(),
               "in_archive": r is not None}
        if r is not None:
            m_dec, m_fill = minute_of(close) - 1, minute_of(et)
            md, mf = mid(r, m_dec), mid(r, m_fill)
            m1, m5 = mid(r, m_fill + 1), mid(r, m_fill + 5)
            row.update({"signal_to_fill_per_lot": None if md is None else (p["entry_premium"] - md) * lot,
                        "fill_over_fill_minute_mid_per_lot": None if mf is None else (p["entry_premium"] - mf) * lot,
                        "move_after_1m_per_lot": None if (mf is None or m1 is None) else (m1 - mf) * lot,
                        "move_after_5m_per_lot": None if (mf is None or m5 is None) else (m5 - mf) * lot})
            if p.get("exit_time") and p.get("exit_premium") is not None:
                xt = dt.datetime.fromisoformat(p["exit_time"]).replace(tzinfo=None)
                mx = mid(r, minute_of(xt))
                row["exit_below_mid_per_lot"] = None if mx is None else (mx - p["exit_premium"]) * lot
        rows.append(row)
    ctl1, ctl5 = [], []
    expiries = sorted(qa.manifest()["option_expiries"]["NIFTY"])
    for d in sorted(qdays):
        if d in expiries:
            continue
        q = qa.load(d)
        near = [e for e in expiries if e > d][0]
        f = qa.front_fut(q, "NIFTY")
        if f is None or np.isnan(f["ltp"][45]):
            continue
        strikes = sorted({k[2] for k in q["opt"] if k[0] == "NIFTY" and k[1] == near})
        K = min(strikes, key=lambda s: abs(s - f["ltp"][45]))
        for o in ("CE", "PE"):
            r = q["opt"].get(("NIFTY", near, K, o))
            if r is None:
                continue
            a, b1, b5 = mid(r, 45), mid(r, 46), mid(r, 50)
            if a is not None and b1 is not None:
                ctl1.append((b1 - a) * 65)
            if a is not None and b5 is not None:
                ctl5.append((b5 - a) * 65)
    res = {"paper_entries_in_archive_days": len(rows), "with_quotes": sum(r["in_archive"] for r in rows),
           "delay_seconds": stats([r["delay_s"] for r in rows]),
           "signal_to_fill_per_lot": stats([r.get("signal_to_fill_per_lot") for r in rows]),
           "fill_over_mid_per_lot": stats([r.get("fill_over_fill_minute_mid_per_lot") for r in rows]),
           "move_after_fill_1m_per_lot": stats([r.get("move_after_1m_per_lot") for r in rows]),
           "move_after_fill_5m_per_lot": stats([r.get("move_after_5m_per_lot") for r in rows]),
           "exit_below_mid_per_lot": stats([r.get("exit_below_mid_per_lot") for r in rows]),
           "scheduled_10am_move_1m_per_lot": stats(ctl1), "scheduled_10am_move_5m_per_lot": stats(ctl5)}
    print(json.dumps(res, indent=1), flush=True)
    for r in rows:
        print("  ", {k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items()})
    res["rows"] = rows
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
