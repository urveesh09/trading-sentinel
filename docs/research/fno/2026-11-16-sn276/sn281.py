"""SN281 - cheaper expressions of the two signals positive on unseen data (PLAN.md; description only, both post-hoc):
pre-holiday sessions (09:20 -> 15:10) and the 10-day breakout swing (15:15 -> next session 15:15, 1-ATR index stop on
15-minute marks). Expressions: the ATM option, the ITM option (one strike in), and the debit spread (buy ATM, sell two
strikes out). Rs 3,000 stop, one lot. DEV, TEST, EXAM-N, EXAM-S."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SN251 = HERE.parent / "2026-11-16-sn251"
sys.path.insert(0, str(SN251))
import gl  # noqa: E402
import legs as LG  # noqa: E402
import sn258  # noqa: E402
import sn259  # noqa: E402


def expr(smp, s, i, side, kind):
    K = gl.atm(smp, s, i)
    st = smp.mk["step"]
    o = "CE" if side > 0 else "PE"
    if kind == "ATM":
        return [(K, o, 1)]
    if kind == "ITM":
        return [(K - st if side > 0 else K + st, o, 1)]
    return [(K, o, 1), (K + 2 * st if side > 0 else K - 2 * st, o, -1)]


def pre_holiday(kind):
    def f(smp, d):
        if not sn259.pre_holiday(smp, d):
            return None
        return LG.intraday(smp, d, expr(smp, smp.s[d], gl.I["09:20"], 1, kind), gl.I["09:20"], gl.FLAT)
    return f


def swing(kind):
    def f(smp, d):
        sd = sn258.sig_break(smp, d)
        if not sd:
            return None
        n1 = LG.next_session(smp, d)
        a = sn258.atr14(smp, d)
        if n1 is None or not a:
            return None
        lvl = float(smp.s[d]["index"][3][sn258.IE])

        def stop_for(dd):
            idx = smp.s[dd]["index"][3]
            return lambda j: j % 15 == 0 and ((sd > 0 and idx[j] < lvl - a) or (sd < 0 and idx[j] > lvl + a))
        return LG.held(smp, d, expr(smp, smp.s[d], sn258.IE, sd, kind), sn258.IE, [(d, gl.NM - 1), (n1, sn258.IE)],
                       stop_index_by_day=stop_for)
    return f


if __name__ == "__main__":
    out = HERE / "results-sn281.json"
    if out.exists():
        raise SystemExit("SN281 is run once")
    for n in ("EXAMN", "EXAMS"):
        gl.SEALED[n] = True
    res = {}
    for sig, mk in (("pre-holiday", pre_holiday), ("10-day breakout swing", swing)):
        for kind in ("ATM", "ITM", "debit spread"):
            row = {}
            for n in ("DEV", "TEST", "EXAMN", "EXAMS"):
                st = gl.stats(gl.book(gl.sample(n), mk(kind)))
                row[n] = {k: st[k] for k in ("trades", "net", "per_trade", "win_pct", "worst", "by_year")}
            row["all_four_positive"] = all(row[n]["net"] > 0 for n in ("DEV", "TEST", "EXAMN", "EXAMS"))
            row["total"] = sum(row[n]["net"] for n in ("DEV", "TEST", "EXAMN", "EXAMS"))
            res[f"{sig} | {kind}"] = row
            print("SN281", sig, kind, json.dumps({n: (row[n]["trades"], row[n]["net"]) for n in ("DEV", "TEST", "EXAMN", "EXAMS")}),
                  "total", row["total"], "all four +", row["all_four_positive"], flush=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
