"""SN426: reconcile the dates and every entry decision (PLAN.md section 1, frozen at 123301ac; details fixed here before
any number). Read only; learning only.

Dates: every NIFTY session in Breeze's daily bars (Jan 3, 2022 - Oct 28, 2026), labelled
  GOLD_SESSION   in Gold's replay (DEPLOYED 2022-26 day list)
  EXPIRY         the date is a NIFTY weekly expiry: in Gold's sessions' front expiries or in Breeze's option request keys
  SPECIAL        no regular index minute at 09:15-09:20 (a muhurat evening or a special session)
  DATA_HOLE      regular index minutes exist, not an expiry, not in Gold's data
  UNRESOLVED     none of these
with per-date evidence for the auditor's 12 unmatched dates (weekday, first / last index minute, option request keys
that cover the date, Gold neighbours).
Signals: every N11 / R0.85 stream signal 2022-26 against Gold's log (Rs 205): TAKEN, DUPLICATE (another book's signal at
the same day and minute was taken), BUSY (a Gold position open at its minute), LATE (at or after Gold's last entry
minute), EXPIRY_MISMATCH, DAY_STOP (Gold's day room at that minute < 5% of it), OTHER. By year and expert.
Per-market-session net with every calendar session in the denominator (Rs 205 / 400).
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-17-sn411"))
import gold  # noqa: E402

OUT = HERE / "results-sn426.json"
HIST = Path(r"C:/Users/Urveesh/sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite")
TWELVE = ("2022-01-12", "2022-03-29", "2022-03-30", "2022-03-31", "2022-05-31", "2022-06-14", "2022-10-24", "2023-03-01", "2023-11-12",
          "2024-11-01", "2025-10-21", "2025-12-31")


def main():
    if OUT.exists():
        raise SystemExit("SN426 is run once")
    con = sqlite3.connect(f"file:{HIST.as_posix()}?mode=ro", uri=True)
    cal = sorted({r[0][:10] for r in con.execute("SELECT datetime FROM candles WHERE underlying='NIFTY' AND kind='daily' AND interval='1day' AND datetime>=? AND datetime<=?",
                                                    ("2022-01-01", "2026-10-28 23:59"))})
    res = {}
    for st in (205.0, 400.0):
        days, log, _ = gold.run(gold.Y2226, gold.DEPLOYED, st)
        res[f"per_calendar_session@{int(st)}"] = round(sum(n for _d, _w, n, *_r in days) / len(cal), 2)
        if st == 205.0:
            g_days, g_log = days, log
    gold_days = {d for d, *_ in g_days}
    exp_gold = set()
    sess_exp = {}
    for y in gold.Y2226:
        for S in gold.C.years()[y].ordered():
            exp_gold.add(S.s["expiry"])
            sess_exp[S.day] = S.s["expiry"]
    exp_keys = set()
    for (k,) in con.execute("SELECT key FROM requests WHERE key LIKE 'option|NIFTY|%' AND status='ok'"):
        exp_keys.add(k.split("|")[2])
    labels, evidence = {}, {}
    for d in cal:
        if d in gold_days:
            labels[d] = "GOLD_SESSION"
            continue
        first = con.execute("SELECT MIN(datetime), MAX(datetime), COUNT(*) FROM candles WHERE underlying='NIFTY' AND kind='index' AND interval='1minute' AND datetime>=? AND datetime<?",
                            (d, d + "~")).fetchone()
        reg = con.execute("SELECT COUNT(*) FROM candles WHERE underlying='NIFTY' AND kind='index' AND interval='1minute' AND datetime>=? AND datetime<=?",
                          (d + " 09:15", d + " 09:20")).fetchone()[0]
        if d in exp_gold or d in exp_keys:
            lab = "EXPIRY"
        elif reg == 0:
            lab = "SPECIAL"
        elif first[2]:
            lab = "DATA_HOLE"
        else:
            lab = "UNRESOLVED"
        labels[d] = lab
        if d in TWELVE:
            cover = [k for (k,) in con.execute("SELECT key FROM requests WHERE key LIKE 'option|NIFTY|%' AND status='ok' AND substr(key, -21, 10) <= ? AND substr(key, -10) >= ? LIMIT 3", (d, d))]
            evidence[d] = {"label": lab, "weekday": dt.date.fromisoformat(d).strftime("%a"), "index_first": first[0], "index_last": first[1], "index_minutes": first[2],
                           "regular_0915_0920": reg, "option_keys_covering": cover, "in_expiry_keys": d in exp_keys, "in_gold_front_expiries": d in exp_gold}
    res["date_labels"] = dict(collections.Counter(labels.values()))
    res["date_labels_by_year"] = {y: dict(collections.Counter(v for d, v in labels.items() if d[:4] == y)) for y in gold.Y2226}
    res["twelve"] = evidence
    res["non_gold_dates"] = {d: v for d, v in labels.items() if v != "GOLD_SESSION" and v != "EXPIRY"}
    # signals
    by_day = collections.defaultdict(list)
    for t in g_log:
        by_day[t["day"]].append(t)
    taken = {(t["day"], t["i"]) for t in g_log}
    exit_min = gold.L.M.EXIT_MIN
    loss_share = 0.2
    wal = {d: w for d, w, *_ in g_days}
    sigs = []
    for y in gold.Y2226:
        for b in gold.DEPLOYED:
            for s in gold.P.stream(y, b):
                sigs.append(s)
    cls = []
    for s in sigs:
        d, i = s["day"], s["i"]
        if d not in gold_days:
            c = "NOT_A_GOLD_SESSION"
        elif (d, i) in taken and any(t["i"] == i and t.get("expert") == s["expert"] and t.get("opt") == s["opt"] for t in by_day[d]):
            c = "TAKEN"
        elif (d, i) in taken:
            c = "DUPLICATE"
        elif any(t["i"] <= i < t["j"] for t in by_day[d]):
            c = "BUSY"
        elif i >= exit_min:
            c = "LATE"
        elif s["expiry"] != sess_exp.get(d):
            c = "EXPIRY_MISMATCH"
        else:
            realized = sum(t["net"] for t in by_day[d] if t["j"] <= i)
            room = loss_share * wal.get(d, 30000.0) + realized
            c = "DAY_STOP" if room < 0.05 * loss_share * wal.get(d, 30000.0) else "OTHER"
        cls.append({"day": d, "i": i, "book": s["book"], "expert": s["expert"], "class": c})
    res["signals"] = len(cls)
    res["signal_classes"] = dict(collections.Counter(c["class"] for c in cls))
    res["signal_classes_by_year"] = {y: dict(collections.Counter(c["class"] for c in cls if c["day"][:4] == y)) for y in gold.Y2226}
    res["signal_classes_by_book"] = {b: dict(collections.Counter(c["class"] for c in cls if c["book"] == b)) for b in gold.DEPLOYED}
    res["untaken_on_traded_days"] = sum(1 for c in cls if c["class"] in ("BUSY", "DUPLICATE", "LATE", "EXPIRY_MISMATCH", "DAY_STOP", "OTHER") and by_day.get(c["day"]))
    res["other_examples"] = [c for c in cls if c["class"] == "OTHER"][:20]
    res["calendar_sessions"], res["gold_sessions"], res["gold_trades"] = len(cal), len(gold_days), len(g_log)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("non_gold_dates", "other_examples")}, indent=1))


if __name__ == "__main__":
    main()
