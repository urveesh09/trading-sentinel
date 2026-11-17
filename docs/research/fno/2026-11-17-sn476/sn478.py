"""SN478: the same Gold entry, sooner (PLAN.md SN478, frozen at bf895633; details fixed here before any number).

Live latency (the SN476 receipt): N11_PAPER rows: entry_time - (bar_ts + 5 min); NIFTY fno_signals rows since Nov 2: evaluated_at
(UTC -> IST) - (bar_ts + 5 min). Median, p10, p90, n.
Replay latency: the DEPLOYED stream (N11 + R0.85 evals, sn392.stream's reading plus bar_ts): entry minute - bar-end minute
(minute_of(bar_ts) + 5, whose close is bar_ts + 5:59), counted 0 / 1 / 2+ minutes.
Diagnostic: for each later entry, was the stream contract (N11's strike) untraded at the bar-end minute in the replay's data
(the session's option record, traded flag false)?
FAST arm: the stream's i -> the bar-end minute when later; in Gold's gold_one, if the stream contract has no replay quote at that
minute (L.quote is None) the original minute is used (counted). Contract choice, sizing, stop, add, N11 exit minute: Gold's rules.
Scored on GOLD_30K and ONE_15K, both paths, Rs 205 / 400, with sn480.compare. Trades matched across arms by (day, N11 strike,
side, N11 exit minute); Gold trades without a FAST counterpart are listed with their net ("missed").
PASS: GOLD_30K paired net > 0 at both stresses in both paths and no Gold winner missed.
Archive check: the live N11_PAPER rows' entry asks against the quote archive's last record of the same front-weekly contract in the
bar-end minute and in the minute after it.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FNO / "2026-11-13-sn101"))
import sn480 as A  # noqa: E402
import sn476  # noqa: E402

goldx, g = A.goldx, A.g
OUT = HERE / "results-sn478.json"
N11L = FNO.parent / "simulation" / "2026-11-02-fno-n11" / "_local"
SN366L = FNO / "2026-11-16-sn366" / "_local"
SRC = {"N11": ("panel", "N11", "panel|N11"), "R0.85": ("panel", "R0.85", "panel|R0.85")}
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
MODE = {"fast": False}
COUNT = collections.Counter()
_orig_stream = g._orig_stream


def stream_bar(year, book):
    phase, name, exam = SRC[book]
    if year == "2022":
        key = json.loads((SN366L / "keys-exam-2022.json").read_text(encoding="utf-8"))[exam]
        data = json.loads((SN366L / "exam-evals-2022" / f"{key}.json").read_text(encoding="utf-8"))
    else:
        key = json.loads((N11L / f"keys-{phase}-{year}.json").read_text(encoding="utf-8"))[name]
        data = json.loads((N11L / "evals" / f"{key}.json").read_text(encoding="utf-8"))
    out = []
    for t in data["trades"]:
        ctx = t["n091_entry"]["native_gate_context"]
        sym = t["tradingsymbol"]
        i = g.B.minute_of(t["entry_time"])
        bar_end = g.B.minute_of(t["bar_ts"].replace(" ", "T")) + 5
        out.append({"day": t["entry_time"][:10], "i": i, "j": g.B.minute_of(t["exit_time"]), "strike": int(round(ctx["strike"])),
                    "opt": "CE" if ctx["is_call"] else "PE", "expiry": f"20{sym[5:7]}-{sym[7:9]}-{sym[9:11]}", "reason": t["exit_reason"],
                    "expert": t["entry_expert"], "gate": t.get("entry_gate") or "", "book": book,
                    "sig_key": (t["entry_time"][:16], int(round(ctx["strike"])), ctx["is_call"]), "bar_ts": t["bar_ts"], "bar_end": bar_end, "i_orig": i})
    return out


def dispatch(year, book="N11"):
    xs = stream_bar(year, book)
    if MODE["fast"]:
        xs = [{**x, "i": x["bar_end"]} if x["bar_end"] < x["i"] else x for x in xs]
    return xs


_gold_one = None


def fast_gold_one(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss):
    if MODE["fast"] and sg.get("i_orig") is not None and sg["i"] < sg["i_orig"]:
        if goldx.L.quote(S, sg["strike"], sg["opt"], sg["i"]) is None:
            COUNT["kept_original_no_quote"] += 1
            sg = {**sg, "i": sg["i_orig"]}
        else:
            COUNT["moved_earlier"] += 1
    return _gold_one(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss)


def pct(xs):
    xs = sorted(xs)
    if not xs:
        return None
    q = lambda p: round(float(np.quantile(xs, p)), 1)  # noqa: E731
    return {"n": len(xs), "median": q(0.5), "p10": q(0.1), "p90": q(0.9), "min": round(xs[0], 1), "max": round(xs[-1], 1)}


def live_latency():
    rec = sorted((HERE / "_local").glob("prod-gold-*.json"))[-1]
    P = json.loads(rec.read_bytes())
    paper = []
    for r in P["fno_n11_paper"]:
        if r["source"] != "N11_PAPER":
            continue
        end = dt.datetime.fromisoformat(r["bar_ts"]).replace(tzinfo=IST) + dt.timedelta(minutes=5)
        paper.append({"id": r["id"], "bar_ts": r["bar_ts"], "entry_time": r["entry_time"], "lag_s": round((dt.datetime.fromisoformat(r["entry_time"]) - end).total_seconds(), 1),
                      "symbol": r["tradingsymbol"], "ask": r["entry_premium"]})
    ev = []
    for s in P["fno_signals"]:
        if s["underlying"] != "NIFTY" or not s.get("bar_ts"):
            continue
        end = dt.datetime.fromisoformat(s["bar_ts"]).replace(tzinfo=IST) + dt.timedelta(minutes=5)
        ev.append((dt.datetime.fromisoformat(str(s["evaluated_at"]).replace("Z", "+00:00")) - end).total_seconds())
    return paper, {"paper_rows": pct([p["lag_s"] for p in paper]), "nifty_evaluations": pct(ev),
                   "nifty_evaluations_within_0_300s": pct([x for x in ev if 0 <= x <= 300])}


def archive_check(paper):
    import qa
    qa.EXPORT = sn476.EXPORT
    qa.LOCAL = HERE / "_local" / "qa"
    out = []
    for p in paper:
        day = p["entry_time"][:10]
        q = qa.load(day)
        strike, opt = int(p["symbol"][-7:-2]), p["symbol"][-2:]
        exps = sorted({k[1] for k in q["opt"] if k[0] == "NIFTY" and k[1] >= day})
        rec = q["opt"].get(("NIFTY", exps[0], strike, opt)) if exps else None
        bar_end = int(p["bar_ts"][11:13]) * 60 + int(p["bar_ts"][14:16]) + 5 - 555
        row = {"id": p["id"], "lag_s": p["lag_s"], "live_ask": p["ask"]}
        if rec is not None:
            for tag, m in (("ask_bar_end_minute_last", bar_end), ("ask_next_minute_last", bar_end + 1)):
                v = rec["ask"][m] if rec["usable"][m] else np.nan
                row[tag] = None if np.isnan(v) else float(v)
        out.append(row)
    return out


def match_key(t):
    return (t["day"], t.get("n11_strike"), t.get("opt"), t.get("sig_j"))


def main():
    global _gold_one
    if OUT.exists():
        raise SystemExit("SN478 is scored once")
    goldx.install()
    g._orig_stream = dispatch
    _gold_one = g.C.gold_one
    g.C.gold_one = fast_gold_one
    res = {}
    paper, res["live_latency_s"] = live_latency()
    res["live_paper_rows"] = paper
    res["archive_check"] = archive_check(paper)
    lag, diag = collections.Counter(), collections.Counter()
    for pname, years in A.PATHS:
        for y in years:
            seen = {}
            for b in g.DEPLOYED:
                for x in stream_bar(y, b):
                    seen.setdefault(x["sig_key"], x)
            for x in seen.values():
                d = x["i"] - x["bar_end"]
                lag[f"{pname} +{d if d < 2 else '2+'} min"] += 1
    res["replay_latency_minutes_after_bar_end_minute"] = dict(sorted(lag.items()))
    cells = {}
    for lname, wallet in (("GOLD_30K", goldx.GOLD_30K), ("ONE_15K", goldx.ONE_15K)):
        for pname, years in A.PATHS:
            for st in A.STRESSES:
                MODE["fast"] = False
                sb, db, lb = A.run(years, st, wallet)
                COUNT.clear()
                MODE["fast"] = True
                sc, dc, lc = A.run(years, st, wallet)
                MODE["fast"] = False
                c = A.compare(sb, db, lb, sc, dc, lc)
                kc = {match_key(t) for t in lc}
                kb = {match_key(t) for t in lb}
                c.update(moved=dict(COUNT), missed=[[t["day"], t["i"], t.get("expert"), round(t["net"])] for t in lb if match_key(t) not in kc],
                         new=[[t["day"], t["i"], t.get("expert"), round(t["net"])] for t in lc if match_key(t) not in kb],
                         entry_minute_changed=sum(1 for t in lc if match_key(t) in kb and t["i"] != next(u["i"] for u in lb if match_key(u) == match_key(t))))
                c.pop("fail_events", None)
                cells[f"{lname} {pname} @{int(st)}"] = c
                if lname == "GOLD_30K" and st == 205.0:
                    Ys = g.C.years()
                    for y in years:
                        Y = Ys[y]
                        for b in g.DEPLOYED:
                            for x in stream_bar(y, b):
                                if x["i"] > x["bar_end"] and x["day"] in Y.sessions:
                                    r = Y.sessions[x["day"]].option(x["strike"], x["opt"])
                                    diag[f"{pname} later entry: N11 contract {'untraded' if r is None or not r[6][x['bar_end']] else 'traded'} at the bar-end minute"] += 1
    res["diagnostic_later_entries"] = dict(diag)
    res["cells"] = cells
    assert cells["GOLD_30K 2023-2026 @205"]["gold"]["net"] in (850882, 850883), cells["GOLD_30K 2023-2026 @205"]["gold"]["net"]
    ok = all(cells[f"GOLD_30K {p} @{int(s)}"]["diff_total"] > 0 for p, _y in A.PATHS for s in A.STRESSES)
    missed_winners = sum(1 for p, _y in A.PATHS for s in A.STRESSES for m in cells[f"GOLD_30K {p} @{int(s)}"]["missed"] if m[3] > 0)
    res["verdict"] = {"PASS" if ok and missed_winners == 0 else "FAIL": {"paired_positive_everywhere": ok, "missed_gold_winners": missed_winners}}
    OUT.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("live_latency_s", "replay_latency_minutes_after_bar_end_minute", "diagnostic_later_entries", "verdict")}, indent=1))
    for r in res["archive_check"]:
        print(r)
    for k, c in cells.items():
        print(f"{k:24s} gold {c['gold']['net']:>9} fast {c['challenger']['net']:>9} diff {c['diff_total']:>8} ci {c['diff_ci90']} w/o {c['diff_without_most_affected']:>8} "
              f"worst {c['worst_day']} moved {c['moved']} missed {len(c['missed'])} new {len(c['new'])} changed {c['entry_minute_changed']}")


if __name__ == "__main__":
    main()
