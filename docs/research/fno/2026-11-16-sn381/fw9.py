"""SN394 forward arm: the auction-direction ITM trade on CHEAP opens only, frozen Nov 16, 2026 before any forward session
(sn394b's gate passed: permutation p 0.031 at both stresses, positive in both protocol periods; the best of ~10 splits,
so this is a test, not a belief).

Per recorder session (sn301's verified nightly archive):
  trade    fw7a.session (SN381's honest rules: walked cost + charges <= Rs 15,000, capped limit, signal received before
           09:16:00, paired controls ATM and coin-ITM)
  jump     IV(09:16:00) - IV(previous archived session's 15:00:00), vol points: Black-76 straddle IV of the front-weekly
           ATM pair on recorder mids (last valid packet at or before the clock), synthetic forward K + C - P, expiry at
           15:30; the previous session must have the same front expiry, else no reading (as SN377)
  CHEAP    jump < 1.2684 (the lower tercile of 644 historical jumps, gl 2022 - Oct 2026, frozen here; upper 3.0684)
  only CHEAP sessions trade; others are NOT_ELIGIBLE and score 0 per session
Verdict once: when 15 CHEAP fills exist or after 60 qualified non-expiry sessions from Nov 17 (whichever first), with
fw7a.judge on the CHEAP rows (PASS = per-session > 0 at Rs 205 and Rs 400, paired lift > 0 vs both controls with >= 10
common fills, > 0 without the best day) and the per-session net over all qualified sessions reported beside it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FNO / "2026-11-16-sn351"))
import fw7a  # noqa: E402

LO_CUT, HI_CUT = 1.2684, 3.0684
OUT = HERE / "results-sn394-fw9.json"
MIN_FILLS, MAX_SESSIONS = 15, 60


def straddle_iv(day, t, hhmm):
    import sn361
    k = day.atm(t)
    if k is None:
        return None
    mids = []
    for o in ("CE", "PE"):
        tok = day.opt.get((day.front, k, o))
        d = None if tok is None else day.D.get(tok)
        if d is None or "bid" not in d:
            return None
        j = int(np.searchsorted(d["t"], t, side="right")) - 1
        while j >= 0 and not d["ok"][j]:
            j -= 1
        if j < 0:
            return None
        mids.append(0.5 * (d["bid"][j] + d["ask"][j]))
    F = k + mids[0] - mids[1]
    return None if F <= 0 else sn361.iv(mids[0] + mids[1], F, k, sn361.years_to(day.day, day.front, hhmm))


def jump_of(folder, prev_folder):
    import fw2
    import fw5
    import fw6
    if prev_folder is None:
        return None, "no_previous_session"
    today = fw2.Day(folder, fw5.load_open(folder))
    names = {p.name for p in Path(prev_folder).glob("chunk-*.bin.xz") if "145500" <= p.name[6:12] < "150200"}
    prev = fw2.Day(prev_folder, fw6._load(Path(prev_folder), names))
    if prev.front != today.front:
        return None, "expiry_changed"
    a, b = straddle_iv(today, 60.0, "09:16"), straddle_iv(prev, 20700.0, "15:00")
    if a is None or b is None:
        return None, "no_quote"
    return 100.0 * (a - b), "ok"


def verdict():
    import fw5
    if OUT.exists():
        raise SystemExit("fw9 is scored once")
    days = sorted(p.name for p in fw5.ARCH.iterdir() if p.is_dir()) if fw5.ARCH.exists() else []
    rows, allrows, prev = [], [], None
    for d in days:
        folder = fw5.ARCH / d
        if d < fw5.START:
            prev = folder
            continue
        rc = fw5.REC / f"{d}.json"
        q = json.loads(rc.read_text(encoding="utf-8")).get("qualify", {}) if rc.exists() else {}
        r = fw7a.session(folder) if q.get("ok") else {"skip": "not qualified"}
        if not r.get("skip"):
            j, why = jump_of(folder, prev)
            r["jump"], r["jump_status"] = j, why
            r["cheap"] = j is not None and j < LO_CUT
            if not r["cheap"]:
                for arm in ("ITM", "ATM", "COIN_ITM"):
                    if isinstance(r.get(arm), dict):
                        r[arm] = {**r[arm], "state": "NOT_ELIGIBLE", "net205": 0.0, "net400": 0.0}
            allrows.append(r)
            if r["cheap"]:
                rows.append(r)
        prev = folder
        fills = sum(1 for x in rows if x["ITM"]["state"] in ("FILLED", "UNRESOLVED"))
        if fills >= MIN_FILLS or len(allrows) >= MAX_SESSIONS:
            break
    fills = sum(1 for x in rows if x["ITM"]["state"] in ("FILLED", "UNRESOLVED"))
    if fills < MIN_FILLS and len(allrows) < MAX_SESSIONS:
        raise SystemExit(f"{fills} CHEAP fills over {len(allrows)} sessions; the verdict waits")
    per_all = {st: round(float(np.mean([x["ITM"].get(f"net{st}", 0.0) if x.get("cheap") and x["ITM"]["state"] in ("FILLED", "UNRESOLVED") else 0.0
                                        for x in allrows])), 1) for st in (205, 400)}
    res = {"sessions": [x.get("day") for x in allrows], "cheap_sessions": len(rows), "CHEAP": fw7a.judge(rows) if rows else None,
           "per_session_all": per_all, "rows": allrows}
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "dev":
        f = Path(sys.argv[2])
        j, why = jump_of(f, f)                    # plumbing only: the same folder stands in for the previous session
        print(json.dumps({"jump_same_day_standin": j, "status": why, "cheap_if_real": None if j is None else j < LO_CUT}))
    elif len(sys.argv) > 1 and sys.argv[1] == "verdict":
        verdict()
    else:
        raise SystemExit("usage: fw9.py dev FOLDER | verdict")
