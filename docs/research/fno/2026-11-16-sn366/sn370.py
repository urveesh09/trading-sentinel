"""SN370: is NIFTY busier at 10:30 IST when Hong Kong's afternoon session reopens? (PLAN.md section 1: no HK quotes exist
here, so this is the feed-justification check; details fixed here before any SN370 number.)

HK afternoon closed = HK general holidays (gov.hk pages for 2022 - 2026, fetched Nov 16, 2026, listed below) plus HKEX's
half days with no afternoon session (Christmas Eve, New Year's Eve, Lunar New Year's Eve, when weekdays). Typhoon /
black-rainstorm closures are irregular and not included (some "open" days were really closed: a bias toward no effect).
Sessions: gl DEV + TEST NIFTY, Apr 2022 - Oct 28, 2026, non-expiry. Groups: HK_OPEN (Indian sessions with HK's afternoon
session) and HK_CLOSED.
Per session and clock c in {10:00, 10:30 (the reopen), 11:00} (entry two minutes before: 09:58 / 10:28 / 10:58):
  absolute index return entry -> +17 minutes (basis points);
  the ATM straddle bought at the entry minute (gl model), sold 17 and 32 minutes later, net at stress 0 / 205.
Result: diff(c) = HK_OPEN - HK_CLOSED mean absolute return; DiD = diff(10:30) - mean(diff(10:00), diff(11:00)), with a
5,000-draw label-shuffle p-value. Close (no feed is worth buying) unless DiD > 0 with p < 0.10.
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn371 as S  # noqa: E402

gl = S.gl
OUT = HERE / "results-sn370.json"
HK_GENERAL = {
    "2022": ["01-01", "02-01", "02-02", "02-03", "04-05", "04-15", "04-16", "04-18", "05-02", "05-09", "06-03", "07-01", "09-12", "10-01", "10-04", "12-26", "12-27"],
    "2023": ["01-02", "01-23", "01-24", "01-25", "04-05", "04-07", "04-08", "04-10", "05-01", "05-26", "06-22", "07-01", "09-30", "10-02", "10-23", "12-25", "12-26"],
    "2024": ["01-01", "02-10", "02-12", "02-13", "03-29", "03-30", "04-01", "04-04", "05-01", "05-15", "06-10", "07-01", "09-18", "10-01", "10-11", "12-25", "12-26"],
    "2025": ["01-01", "01-29", "01-30", "01-31", "04-04", "04-18", "04-19", "04-21", "05-01", "05-05", "05-31", "07-01", "10-01", "10-07", "10-29", "12-25", "12-26"],
    "2026": ["01-01", "02-17", "02-18", "02-19", "04-03", "04-04", "04-06", "04-07", "05-01", "05-25", "06-19", "07-01", "09-26", "10-01", "10-19", "12-25", "12-26"],
}
LNY_EVE = ["2022-01-31", "2024-02-09", "2025-01-28", "2026-02-16"]          # 2023's eve (Jan 21) was a Saturday
CLOCKS = {"10:00": 43, "10:30": 73, "11:00": 103}                          # entry minute = clock - 2 minutes


def hk_closed_days():
    out = {f"{y}-{md}" for y, mds in HK_GENERAL.items() for md in mds}
    for y in ("2022", "2023", "2024", "2025", "2026"):
        for md in ("12-24", "12-31"):
            d = dt.date.fromisoformat(f"{y}-{md}")
            if d.weekday() < 5:
                out.add(d.isoformat())
    out |= set(LNY_EVE)
    return out


def straddle(smp, s, i, j, st):
    k = gl.atm(smp, s, i)
    pos = gl.Pos(smp, s, [(k, "CE", +1), (k, "PE", +1)], i, lots=1, stress=st)
    if not pos.ok:
        return None
    v = None
    for jj in range(j, j - 3, -1):
        v = pos.value(s, jj)
        if v is not None:
            break
    return v


def main():
    if OUT.exists():
        raise SystemExit("SN370 is run once")
    raw = gl._cache("devall", gl.build_dev)
    smp = gl.Sample("ALL", raw, gl.DEV_LO, gl.TEST_HI)
    closed = hk_closed_days()
    rows = []
    for d in smp.days:
        s = smp.s[d]
        if s["day"] == s["expiry"]:
            continue
        idx = s["index"][3]
        r = {"day": d, "group": "HK_CLOSED" if d in closed else "HK_OPEN"}
        for c, i in CLOCKS.items():
            a, b = idx[i], idx[i + 17]
            r[f"abs {c}"] = None if np.isnan(a) or np.isnan(b) else abs(float(b) / float(a) - 1.0) * 1e4
            for st in (0.0, 205.0):
                for h in (17, 32):
                    r[f"strad {c} {h}m@{int(st)}"] = straddle(smp, s, i, i + h, st)
        rows.append(r)

    def mean(group, key):
        xs = [r[key] for r in rows if r["group"] == group and r.get(key) is not None]
        return float(np.mean(xs)) if xs else None
    res = {"sessions": len(rows), "hk_closed_sessions": sum(r["group"] == "HK_CLOSED" for r in rows)}
    for g in ("HK_OPEN", "HK_CLOSED"):
        res[g] = {k: (round(mean(g, k), 2) if mean(g, k) is not None else None) for k in rows[0] if k not in ("day", "group")}
    diff = {c: res["HK_OPEN"][f"abs {c}"] - res["HK_CLOSED"][f"abs {c}"] for c in CLOCKS}
    did = diff["10:30"] - 0.5 * (diff["10:00"] + diff["11:00"])
    labels = [r["group"] for r in rows]
    rng = random.Random(370)
    hits = 0
    for _ in range(5000):
        rng.shuffle(labels)

        def m(g, c):
            xs = [r[f"abs {c}"] for r, lab in zip(rows, labels) if lab == g and r.get(f"abs {c}") is not None]
            return float(np.mean(xs))
        dd = {c: m("HK_OPEN", c) - m("HK_CLOSED", c) for c in CLOCKS}
        hits += (dd["10:30"] - 0.5 * (dd["10:00"] + dd["11:00"])) >= did - 1e-12
    res["diff_bp"] = {c: round(v, 3) for c, v in diff.items()}
    res["DiD_bp"] = round(did, 3)
    res["p_one_sided"] = hits / 5000
    res["close"] = not (did > 0 and res["p_one_sided"] < 0.10)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
