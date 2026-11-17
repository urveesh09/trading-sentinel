"""SN427 B + C: price Gold's expiry-morning candidates (PLAN.md section 1, frozen at 123301ac; details fixed here before
any number). Reads _local/sn427a-<year>.json (2023 - 2026). Development; a pass would only open a forward arm.

Decision: per expiry day, the first candidate (N11 or R0.85, deduplicated) whose clock is 09:20 - 12:30; LONG -> CE,
SHORT -> PE; one lot (65); entry charges + premium <= Rs 15,000; flat by 13:30.
B (Breeze 1-second trades on the expiring contract's opening-ATM strike K0, 87 expiries Jun 2023 - Sep 2026):
  admissible only if |K0 - the index's last completed minute close| <= 50 at the decision (else UNPRICED_STRIKE);
  entry = the close of the first 1-second candle at or after decision + 1 s, + Rs 0.025 (half a tick);
  exits: (1) the premium mark (close - entry) x 65 - charges - stress <= -Rs 3,000, at the next second's close; (2) the
  index's minute close crossing N11's own stop level, at the first second of the next minute; (3) 13:30:00 (the first
  trade at or after); every exit - Rs 0.025. Net after Zerodha charges and Rs 205 / 400.
  Control: a seeded side (random.Random('sn427-' + day)) at the same clock, priced the same way.
C (the real-quote archive, sealed expiry days Sep 10 - Oct 28, 2026 with a candidate): both tenors on the same decision -
  the expiring and the next-week contract at the strike nearest the index; entry at the walked one-lot ask of the first
  usable snapshot after the decision; exits at minute snapshots: the walked-bid mark <= -Rs 3,000, the index crossing
  N11's stop, or 13:30; net after charges and stress.
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import random
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-14-sn201"))
sys.path.insert(0, str(FNO / "2026-11-13-sn101"))
import wk  # noqa: E402
import qa  # noqa: E402

qa.EXPORT = Path(r"C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel"
                 r"\_local\exports\20261116T103002Z")
qa.LOCAL = FNO / "2026-11-17-sn411" / "_local" / "qa"
HIST = Path(r"C:/Users/Urveesh/sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite")
OUT = HERE / "results-sn427.json"
LOT, ROOM, STOP, TICK = 65, 15000.0, 3000.0, 0.05


def charges(b, s):
    return wk.charges(b, s, LOT, "NFO")


def first_candidates():
    cands = []
    for y in ("2023", "2024", "2025", "2026"):
        p = HERE / "_local" / f"sn427a-{y}.json"
        cands += json.loads(p.read_text(encoding="utf-8"))["candidates"]
    by_day = {}
    for c in sorted(cands, key=lambda c: c["at"]):
        t = c["at"][11:19]
        if not ("09:20:00" <= t <= "12:30:00") or c["day"] != c["expiry"]:
            continue
        by_day.setdefault(c["day"], c)
    return by_day, cands


def index_minutes(con, day):
    rows = con.execute("SELECT datetime, close FROM candles WHERE underlying='NIFTY' AND kind='index' AND interval='1minute' AND datetime>=? AND datetime<? ORDER BY datetime",
                       (day, day + "~")).fetchall()
    return [r[0][11:16] for r in rows], [float(r[1]) for r in rows]


def last_close(mins, vals, hhmmss):
    k = bisect.bisect_left(mins, hhmmss[:5]) - 1            # the last minute completed before the decision's minute
    return (mins[k], vals[k]) if k >= 0 else (None, None)


def stop_hit(mins, vals, from_hhmm, side, stop):
    if stop is None:
        return None
    for m, v in zip(mins, vals):
        if m < from_hhmm or m >= "13:30":
            continue
        if (side == "CE" and v <= stop) or (side == "PE" and v >= stop):
            h, mm = int(m[:2]), int(m[3:])
            mm += 1
            return f"{h + mm // 60:02d}:{mm % 60:02d}:00"
    return None


def price_seconds(con, day, k0, side, at, stop, mins, vals, stress):
    rows = con.execute("SELECT datetime, close FROM candles WHERE kind='option' AND underlying='NIFTY' AND interval='1second' AND expiry=? AND strike=? AND opt=? "
                       "AND datetime>=? AND datetime<=? ORDER BY datetime", (day, float(k0), side, day + " 09:15:00", day + " 13:35:00")).fetchall()
    if not rows:
        return {"state": "NO_DATA"}
    ts = [r[0][11:19] for r in rows]
    px = [float(r[1]) for r in rows]
    t_in = (dt.datetime.fromisoformat(at[:19]) + dt.timedelta(seconds=1)).strftime("%H:%M:%S")
    k = bisect.bisect_left(ts, t_in)
    if k >= len(ts):
        return {"state": "NO_DATA"}
    e = px[k] + TICK / 2
    if e * LOT + charges(e, 0.0) > ROOM:
        return {"state": "INADMISSIBLE"}
    idx_exit = stop_hit(mins, vals, ts[k][:5], side, stop)
    for j in range(k + 1, len(ts)):
        mark = (px[j] - e) * LOT - charges(e, px[j]) - stress
        if mark <= -STOP:
            x = px[min(j + 1, len(px) - 1)] - TICK / 2
            return {"state": "FILLED", "net": round((x - e) * LOT - charges(e, x) - stress, 2), "why": "premium_stop", "entry": e, "exit_t": ts[j]}
        if idx_exit is not None and ts[j] >= idx_exit:
            x = px[j] - TICK / 2
            return {"state": "FILLED", "net": round((x - e) * LOT - charges(e, x) - stress, 2), "why": "n11_stop", "entry": e, "exit_t": ts[j]}
        if ts[j] >= "13:30:00":
            x = px[j] - TICK / 2
            return {"state": "FILLED", "net": round((x - e) * LOT - charges(e, x) - stress, 2), "why": "time", "entry": e, "exit_t": ts[j]}
    x = px[-1] - TICK / 2
    return {"state": "FILLED", "net": round((x - e) * LOT - charges(e, x) - stress, 2), "why": "last_print", "entry": e, "exit_t": ts[-1]}


def summ(rows, key):
    xs = [r[key]["net"] for r in rows if r.get(key, {}).get("state") == "FILLED"]
    return {"fills": len(xs), "mean": round(float(np.mean(xs)), 1) if xs else None, "median": round(float(np.median(xs)), 1) if xs else None,
            "winners": sum(x > 0 for x in xs), "total": round(sum(xs)) if xs else 0, "ge_750": sum(x >= 750 for x in xs),
            "without_best": round(float((sum(xs) - max(xs)) / (len(xs) - 1)), 1) if len(xs) > 1 else None}


def part_c(firsts, con):
    man = qa.manifest()
    sealed = [d for d in man["quote_days"] if d not in set(man["unsealed_days"])]
    out = []
    for d, c in sorted(firsts.items()):
        if d not in sealed:
            continue
        q = qa.load(d)
        mins, vals = index_minutes(con, d)
        m, S = last_close(mins, vals, c["at"][11:19])
        if S is None:
            continue
        side = "CE" if c["direction"] == "LONG" else "PE"
        exps = sorted({k[1] for k in q["opt"] if k[0] == "NIFTY" and k[1] >= d})
        i0 = int(c["at"][11:13]) * 60 + int(c["at"][14:16]) - 555 + 1
        row = {"day": d, "at": c["at"], "side": side, "index": S}
        for tenor, e in (("expiring", exps[0] if exps else None), ("next_week", exps[1] if len(exps) > 1 else None)):
            if e is None:
                row[tenor] = {"state": "NO_TENOR"}
                continue
            ks = sorted({k[2] for k in q["opt"] if k[0] == "NIFTY" and k[1] == e and k[3] == side})
            if not ks:
                row[tenor] = {"state": "NO_DATA"}
                continue
            kk = min(ks, key=lambda x: abs(x - S))
            rec = q["opt"][("NIFTY", e, kk, side)]
            j = qa.first_at(rec, i0)
            if j is None:
                row[tenor] = {"state": "NO_DATA"}
                continue
            a = qa.walk_cost(rec["askp"][:, j], rec["askq"][:, j], LOT)
            if a is None or a * LOT + charges(a, 0.0) > ROOM:
                row[tenor] = {"state": "INADMISSIBLE", "strike": kk}
                continue
            idx_exit = stop_hit(mins, vals, c["at"][11:16], side, c.get("stop_underlying"))
            res = {}
            for stress in (205.0, 400.0):
                net, why = None, None
                for x in range(j + 1, 256):
                    if not rec["usable"][x]:
                        continue
                    b = qa.walk_cost(rec["bidp"][:, x], rec["bidq"][:, x], LOT)
                    if b is None:
                        continue
                    hhmm = f"{(555 + x) // 60:02d}:{(555 + x) % 60:02d}"
                    n = (b - a) * LOT - charges(a, b) - stress
                    if n <= -STOP or (idx_exit is not None and hhmm + ":00" >= idx_exit) or x >= 255:
                        net, why = n, ("premium_stop" if n <= -STOP else "n11_stop" if (idx_exit is not None and hhmm + ":00" >= idx_exit) else "time")
                        break
                res[f"net{int(stress)}"] = None if net is None else round(net, 2)
                res["why"] = why
            row[tenor] = {"state": "FILLED" if res.get("net205") is not None else "NO_EXIT", "strike": kk, "ask": round(a, 2), **res}
        out.append(row)
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN427 is scored once")
    firsts, cands = first_candidates()
    con = sqlite3.connect(f"file:{HIST.as_posix()}?mode=ro", uri=True, timeout=60)
    k0s = {r[0]: float(r[1]) for r in con.execute("SELECT expiry, strike FROM expiry_seconds_sessions_v2 WHERE underlying='NIFTY'")}
    res = {"candidates_all": len(cands), "expiry_days_with_candidate": len({c["day"] for c in cands if c["day"] == c["expiry"]}),
           "expiry_days_with_morning_candidate": len(firsts), "by_year": {y: sum(1 for d in firsts if d[:4] == y) for y in ("2023", "2024", "2025", "2026")},
           "candidate_clock_hist": {}, "seconds_data_expiries": len(k0s)}
    for d, c in firsts.items():
        h = c["at"][11:13]
        res["candidate_clock_hist"][h] = res["candidate_clock_hist"].get(h, 0) + 1
    rows = []
    for d, c in sorted(firsts.items()):
        r = {"day": d, "at": c["at"], "direction": c["direction"], "book": c["book"], "stop": c.get("stop_underlying")}
        if d not in k0s:
            r["state"] = "NO_SECONDS_DATA"
            rows.append(r)
            continue
        mins, vals = index_minutes(con, d)
        m, S = last_close(mins, vals, c["at"][11:19])
        k0 = k0s[d]
        r.update(k0=k0, index=S)
        if S is None or abs(k0 - S) > 50:
            r["state"] = "UNPRICED_STRIKE"
            rows.append(r)
            continue
        r["state"] = "PRICED"
        side = "CE" if c["direction"] == "LONG" else "PE"
        coin = random.Random(f"sn427-{d}").choice(("CE", "PE"))
        for st in (205.0, 400.0):
            r[f"signal@{int(st)}"] = price_seconds(con, d, k0, side, c["at"], c.get("stop_underlying"), mins, vals, st)
            r[f"coin@{int(st)}"] = price_seconds(con, d, k0, coin, c["at"], c.get("stop_underlying") if coin == side else None, mins, vals, st)
        rows.append(r)
    res["B_states"] = {s: sum(1 for r in rows if r.get("state") == s) for s in ("PRICED", "UNPRICED_STRIKE", "NO_SECONDS_DATA")}
    pr = [r for r in rows if r.get("state") == "PRICED"]
    for st in (205, 400):
        res[f"B signal @{st}"] = summ(pr, f"signal@{st}")
        res[f"B coin @{st}"] = summ(pr, f"coin@{st}")
    res["B exit reasons"] = {w: sum(1 for r in pr if r.get("signal@205", {}).get("why") == w) for w in ("premium_stop", "n11_stop", "time", "last_print")}
    res["B rows"] = rows
    c_rows = part_c(firsts, con)
    res["C rows"] = c_rows
    for tenor in ("expiring", "next_week"):
        for st in (205, 400):
            xs = [r[tenor][f"net{st}"] for r in c_rows if r.get(tenor, {}).get("state") == "FILLED" and r[tenor].get(f"net{st}") is not None]
            res[f"C {tenor} @{st}"] = {"fills": len(xs), "mean": round(float(np.mean(xs)), 1) if xs else None, "total": round(sum(xs)) if xs else 0, "winners": sum(x > 0 for x in xs)}
    res["C states"] = {t: {s: sum(1 for r in c_rows if r.get(t, {}).get("state") == s) for s in ("FILLED", "INADMISSIBLE", "NO_DATA", "NO_TENOR", "NO_EXIT")} for t in ("expiring", "next_week")}
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("B rows", "C rows")}, indent=1, default=float))


if __name__ == "__main__":
    main()
