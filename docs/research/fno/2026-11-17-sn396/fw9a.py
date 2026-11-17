"""SN396 C: the audit companion of fw9 (frozen Nov 17, 2026, before any forward P&L is seen; PLAN.md section 1 at
00693405). fw9 stays as frozen and its verdict is still produced; this file is published beside it.

What changes from fw9 (the cutoff 1.2684, the clocks 09:16:00 / previous 15:00:00, the IV method and the verdict rule
are fw9's):
  TRADE      fw7b.session (fw7a + the limit-legal fill, zero gap = NO_SIGNAL, exit status per stress)
  FRESH IV   each straddle leg's last valid packet at or before the clock must be <= MAX_AGE old, the call and put
             receipt times <= MAX_SKEW apart, and the index packet that sets the ATM strike <= MAX_AGE old; else no
             reading (STALE). MAX_AGE = MAX_SKEW = 2.0 s: the Nov 16 recorder copy (plumbing only) gave a 99th
             percentile ATM CE / PE inter-packet gap of 1.25 s over 09:15 - 09:20 (index 0.33 s), rounded up to a whole
             second and held to the plan's floor of 2 s.
  PREVIOUS   the previous EXCHANGE session (weekdays minus NSE's holiday list below); if its recording is missing, the
             baseline is MISSING (scored 0, counted), never an older folder. NSE's 2027 list is added when NSE
             publishes it (a fact, disclosed in the README), before any 2027 session is scored.
  ROLL       when the previous session's front expiry differs (the session after an expiry), fw9 has no reading; fw9a
             records a ROLL reading on the SAME contract (today's front was the previous session's next week; the
             recorder holds three expiries). ROLL days are reported in their own block, never in fw9a's verdict.
Verdict once, as fw9: at 15 CHEAP fills or 60 qualified non-expiry sessions from Nov 17 (whichever first).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FNO / "2026-11-16-sn381"))
sys.path.insert(0, str(FNO / "2026-11-16-sn351"))
sys.path.insert(0, str(FNO / "2026-11-16-sn301"))
import fw7a  # noqa: E402
import fw7b  # noqa: E402

LO_CUT = 1.2684
MAX_AGE = MAX_SKEW = 2.0
OUT = HERE / "results-sn396-fw9a.json"
MIN_FILLS, MAX_SESSIONS = 15, 60
HOLIDAYS = frozenset({                         # python-engine/market_calendar.py NSE_HOLIDAYS_STATIC (checked in the tests)
    "2026-01-15", "2026-01-26", "2026-02-15", "2026-03-03", "2026-03-21", "2026-03-26", "2026-03-31", "2026-04-03",
    "2026-04-14", "2026-05-01", "2026-05-28", "2026-06-26", "2026-08-15", "2026-09-14", "2026-10-02", "2026-10-20",
    "2026-11-08", "2026-11-10", "2026-11-24", "2026-12-25"})


# ---- pure rules (tested in test_fw9a.py) ------------------------------------------------------------------------------
def prev_exchange_session(day):
    d = dt.date.fromisoformat(day) - dt.timedelta(days=1)
    while d.weekday() >= 5 or d.isoformat() in HOLIDAYS:
        d -= dt.timedelta(days=1)
    return d.isoformat()


def fresh_at(t_arr, ok_arr, t, max_age=MAX_AGE):
    """Index of the last valid packet at or before t, if it is <= max_age old; else None."""
    j = int(np.searchsorted(t_arr, t, side="right")) - 1
    while j >= 0 and ok_arr is not None and not ok_arr[j]:
        j -= 1
    if j < 0 or t - t_arr[j] > max_age:
        return None
    return j


def straddle_mids(ce, pe, t, max_age=MAX_AGE, max_skew=MAX_SKEW):
    """ce / pe: dicts with t, ok, bid, ask arrays. -> (mid_ce, mid_pe) or None when stale or skewed."""
    jc, jp = fresh_at(ce["t"], ce["ok"], t, max_age), fresh_at(pe["t"], pe["ok"], t, max_age)
    if jc is None or jp is None or abs(ce["t"][jc] - pe["t"][jp]) > max_skew:
        return None
    return 0.5 * (ce["bid"][jc] + ce["ask"][jc]), 0.5 * (pe["bid"][jp] + pe["ask"][jp])


def straddle_iv_fresh(day, t, hhmm, expiry=None):
    import sn361
    expiry = expiry or day.front
    ix = day.D.get(day.idx)
    if ix is None:
        return None, "no_index"
    j = fresh_at(ix["t"], None, t)
    if j is None:
        return None, "stale_index"
    k = int(round(float(ix["ltp"][j]) / 50.0) * 50)
    legs = []
    for o in ("CE", "PE"):
        tok = day.opt.get((expiry, k, o))
        d = None if tok is None else day.D.get(tok)
        if d is None or "bid" not in d:
            return None, "no_contract"
        legs.append(d)
    m = straddle_mids(legs[0], legs[1], t)
    if m is None:
        return None, "stale_or_skewed"
    F = k + m[0] - m[1]
    if F <= 0:
        return None, "bad_forward"
    return sn361.iv(m[0] + m[1], F, k, sn361.years_to(day.day, expiry, hhmm)), "ok"


def jump_of(folder, arch):
    import fw2
    import fw5
    import fw6
    today = fw2.Day(folder, fw5.load_open(folder))
    pd_ = prev_exchange_session(today.day)
    prev_folder = arch / pd_
    if not prev_folder.is_dir():
        return {"jump": None, "status": "MISSING_PREVIOUS", "prev": pd_}
    names = {p.name for p in prev_folder.glob("chunk-*.bin.xz") if "145500" <= p.name[6:12] < "150200"}
    prev = fw2.Day(prev_folder, fw6._load(prev_folder, names))
    a, wa = straddle_iv_fresh(today, 60.0, "09:16")
    if prev.front == today.front:
        b, wb = straddle_iv_fresh(prev, 20700.0, "15:00")
        roll = False
    else:
        b, wb = straddle_iv_fresh(prev, 20700.0, "15:00", expiry=today.front)    # the same contract, one week out then
        roll = True
    if a is None or b is None:
        return {"jump": None, "status": f"STALE ({wa} / {wb})", "prev": pd_, "roll": roll}
    return {"jump": 100.0 * (a - b), "status": "ok", "prev": pd_, "roll": roll}


def verdict():
    import fw5
    if OUT.exists():
        raise SystemExit("fw9a is scored once")
    days = sorted(p.name for p in fw5.ARCH.iterdir() if p.is_dir() and p.name >= fw5.START) if fw5.ARCH.exists() else []
    main, roll, allrows = [], [], []
    for d in days:
        rc = fw5.REC / f"{d}.json"
        q = json.loads(rc.read_text(encoding="utf-8")).get("qualify", {}) if rc.exists() else {}
        if not q.get("ok"):
            continue
        r = fw7b.session(fw5.ARCH / d)
        if r.get("skip"):
            continue
        j = jump_of(fw5.ARCH / d, fw5.ARCH)
        r.update(jump=j["jump"], jump_status=j["status"], roll=j.get("roll", False))
        r["cheap"] = j["jump"] is not None and j["jump"] < LO_CUT
        eligible = r["cheap"] and not r["roll"]
        if r["cheap"] and r["roll"]:
            roll.append(json.loads(json.dumps(r, default=float)))
        if not eligible:
            for arm in ("ITM", "ATM", "COIN_ITM"):
                if isinstance(r.get(arm), dict):
                    r[arm] = {**r[arm], "state": "NOT_ELIGIBLE", "net205": 0.0, "net400": 0.0}
        allrows.append(r)
        if eligible:
            main.append(r)
        fills = sum(1 for x in main if x["ITM"]["state"] in ("FILLED", "UNRESOLVED"))
        if fills >= MIN_FILLS or len(allrows) >= MAX_SESSIONS:
            break
    fills = sum(1 for x in main if x["ITM"]["state"] in ("FILLED", "UNRESOLVED"))
    if fills < MIN_FILLS and len(allrows) < MAX_SESSIONS:
        raise SystemExit(f"{fills} CHEAP fills over {len(allrows)} sessions; the verdict waits")
    per_all = {st: round(float(np.mean([x["ITM"].get(f"net{st}", 0.0) if x in main and x["ITM"]["state"] in ("FILLED", "UNRESOLVED") else 0.0
                                        for x in allrows])), 1) for st in (205, 400)}
    status = {}
    for x in allrows:
        status[x["jump_status"]] = status.get(x["jump_status"], 0) + 1
    res = {"sessions": [x.get("day") for x in allrows], "cheap_sessions": len(main), "CHEAP": fw7a.judge(main) if main else None,
           "per_session_all": per_all, "jump_status": status, "ROLL_block": fw7a.judge(roll) if roll else None, "rows": allrows}
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verdict":
        verdict()
    else:
        raise SystemExit("usage: fw9a.py verdict")
