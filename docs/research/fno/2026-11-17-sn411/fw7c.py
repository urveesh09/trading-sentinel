"""SN411 A: the observability companion of fw7b (frozen Nov 17, 2026, before any forward P&L is seen; PLAN.md section 1
at e5cc95b7). fw7a / fw7b stay as frozen and their verdicts are still produced; this file is published beside them.

What changes from fw7b (everything else is fw7b's rule):
  TODAY'S TRADE  FIRST_TRADE needs a packet received in [09:15:00, 09:16:00] whose exchange last-trade time is at or after
                 today's 09:15:00; a packet carrying an older trade is QUOTE_ONLY and the search goes on. MATCH is fw7a's.
  OFFSET         the receipt-minus-exchange offset is the median over front-future packets received in [08:58:00,
                 09:16:00) only (fw2.Day used the whole day), and every packet's freshness flag is recomputed with it.
  FRESH STRIKE   the index packet that sets the ATM strike must be <= 2.0 s old at 09:16:00, else STALE_INDEX (0).
  FRESH BOOK     the book used for admission and for the cap must be received <= 2.0 s before 09:16:00; a candidate
                 depth with only an older book is unavailable; if no fresh admissible depth exists and a stale one did,
                 the decision is STALE_BOOK (0), else INADMISSIBLE.
Tolerance 2.0 s = fw9a's (the Nov 16 p99 option inter-packet gap 1.25 s, rounded up).
Verdict (once, fw7a's 20 sessions): fw7a.judge on fw7c's rows, with the count of decisions each fix changed.
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-17-sn396"))
import fw7b  # noqa: E402  (puts sn381 / sn351 / sn301 on the path)
import fw7a  # noqa: E402

OUT = HERE / "results-sn411-fw7c.json"
TDEC, HOLD, ROOM = fw7a.TDEC, fw7a.HOLD, fw7a.ROOM
FRESH = 2.0
OFFSET_FROM = -1020.0                          # 08:58:00


# ---- pure rules (tested in test_fw7c.py) ------------------------------------------------------------------------------
def auction_price_c(rows, decision_t, pre0_epoch, cont0_epoch):
    """rows: dicts with t (s after 09:15, receipt), ltp, last_trade_ts (epoch). -> (price, source, receipt t, quote_only)."""
    for r in rows:
        if -420.0 <= r["t"] < 0.0 and r.get("last_trade_ts", 0) >= pre0_epoch:
            return r["ltp"], "MATCH", r["t"], 0
    quote_only = 0
    for r in rows:
        if r["t"] < 0.0:
            continue
        if r["t"] > decision_t:
            break
        if r.get("last_trade_ts", 0) >= cont0_epoch:
            return r["ltp"], "FIRST_TRADE", r["t"], quote_only
        quote_only += 1
    return None, "NO_SIGNAL", None, quote_only


def pre_decision_offset(t, lag, lo=OFFSET_FROM, hi=TDEC):
    m = (t >= lo) & (t < hi) & (np.abs(lag) < 3600)
    return float(np.median(lag[m])) if m.any() else None


def fresh_index(t_arr, ok_arr, at, fresh=FRESH):
    j = int(np.searchsorted(t_arr, at, side="right")) - 1
    while j >= 0 and ok_arr is not None and not ok_arr[j]:
        j -= 1
    if j < 0 or at - t_arr[j] > fresh:
        return None
    return j


# ---- the recorder session ----------------------------------------------------------------------------------------------
def session(folder):
    import fw2
    import fw5
    day = fw2.Day(folder, fw5.load_open(folder))
    out = {"day": day.day, "offset_whole_day": round(day.offset, 4)}
    if day.expiry_day:
        out["skip"] = "expiry_day"
        return out
    f = day.D.get(day.fut)
    if f is None or "buy_qty" not in f:
        out["skip"] = "no_future"
        return out
    off = pre_decision_offset(f["t"], f["lag"])
    out["offset_pre_decision"] = None if off is None else round(off, 4)
    if off is not None:
        day.offset = off
        for d in day.D.values():
            if "bid" in d:
                d["ok"] = (d["bid"] > 0) & (d["ask"] > 0) & (d["ask"] > d["bid"]) & ((d["lag"] - off) <= fw2.FRESH)
    pre0 = fw5.IST.localize(dt.datetime.fromisoformat(day.day + "T09:00:00")).timestamp()
    cont0 = pre0 + 900.0
    rows = [{"t": float(f["t"][k]), "ltp": float(f["ltp"][k]), "last_trade_ts": float(f["last_trade_ts"][k])} for k in range(len(f["t"])) if f["t"][k] >= -900]
    k6 = fw5.last_at(f, fw5.T06)
    C0 = float(f["close"][k6]) if k6 is not None else None
    A, source, at, qonly = auction_price_c(rows, TDEC, pre0, cont0)
    out.update(source=source, signal_receipt_t=at, quote_only_packets=qonly, A=A, C0=C0)
    g = None if (A is None or not C0) else A / C0 - 1.0
    side = fw7b.side_of(g)
    out["g"] = g
    zero = {"net205": 0.0, "net400": 0.0}
    if side is None:
        for arm in ("ITM", "ATM", "COIN_ITM"):
            out[arm] = {"state": "NO_SIGNAL", **zero}
        return out
    ix = day.D.get(day.idx)
    j = None if ix is None else fresh_index(ix["t"], None, TDEC)
    if j is None:
        for arm in ("ITM", "ATM", "COIN_ITM"):
            out[arm] = {"state": "STALE_INDEX", **zero}
        return out
    atm = int(round(float(ix["ltp"][j]) / 50.0) * 50)
    lot, cfn = day.lot, fw7a.charges_buy

    def book_at(tok):
        d = day.D.get(tok)
        if d is None or "asks" not in d:
            return None, False
        k = fresh_index(d["t"], d["ok"], TDEC)
        if k is None:
            kk = int(np.searchsorted(d["t"], TDEC, side="right")) - 1
            while kk >= 0 and not d["ok"][kk]:
                kk -= 1
            return None, kk >= 0
        return (list(d["asks"][:, k]), list(d["askq"][:, k]), float(d["ask"][k]), float(d["t"][k])), False

    def leg(sd, depths=(2, 1)):
        sgn = -1 if sd == "CE" else 1
        books, toks, stale = {}, {}, False
        for dep in depths:
            tok = day.opt.get((day.front, atm + sgn * dep * 50, sd)) if dep else day.opt.get((day.front, atm, sd))
            b, was_stale = (None, False) if tok is None else book_at(tok)
            stale = stale or was_stale
            if b is not None:
                books[dep], toks[dep] = (b[0], b[1]), (tok, b[2], b[3])
        if depths == (0,):
            ok = 0 in books and fw7a.admissible(*books[0], lot, cfn)[0]
            dep, px, cost = (0, *fw7a.admissible(*books[0], lot, cfn)[1:]) if ok else (None, None, None)
        else:
            dep, px, cost = fw7a.pick_depth(books, lot, cfn)
        if dep is None:
            return {"state": "STALE_BOOK" if (stale and not books) else "INADMISSIBLE", **zero}
        tok, ask, qt = toks[dep]
        cap = fw7a.order_cap(ask, lot, cfn)
        r = fw7b.trade_legal(day, tok, TDEC, HOLD, cap)
        r.update(depth=dep, decision_cost=round(cost, 2), cap=round(cap, 2), quote_receipt_t=qt, quote_age=round(TDEC - qt, 3), cash_before=30000.0)
        st = fw7b.state_of(r)
        r["state"] = st
        if st in ("FILLED", "UNRESOLVED"):
            assert r["debit"] <= ROOM + 1e-6, ("room breached", r["debit"])
        else:
            r["net205"] = r["net400"] = 0.0
        return r
    coin = random.Random(f"sn381-{day.day}").choice(("CE", "PE"))
    out["ITM"] = leg(side)
    out["ATM"] = leg(side, depths=(0,))
    out["COIN_ITM"] = leg(coin)
    out["coin_side"] = coin
    return out


def verdict():
    import fw5
    if OUT.exists():
        raise SystemExit("fw7c is scored once")
    days = sorted(p.name for p in fw5.ARCH.iterdir() if p.is_dir() and p.name >= fw5.START) if fw5.ARCH.exists() else []
    rows, skipped, changed = [], [], {"source": 0, "itm_state": 0}
    for d in days:
        rc = fw5.REC / f"{d}.json"
        q = json.loads(rc.read_text(encoding="utf-8")).get("qualify", {}) if rc.exists() else {}
        if not q.get("ok"):
            skipped.append({"day": d, "why": "not qualified"})
            continue
        r = session(fw5.ARCH / d)
        if r.get("skip"):
            skipped.append({"day": d, "why": r["skip"]})
            continue
        b = fw7b.session(fw5.ARCH / d)
        changed["source"] += b.get("source") != r.get("source")
        changed["itm_state"] += (b.get("ITM") or {}).get("state") != (r.get("ITM") or {}).get("state")
        rows.append(r)
        if len(rows) == fw5.N_SESSIONS:
            break
    if len(rows) < fw5.N_SESSIONS:
        raise SystemExit(f"{len(rows)} of {fw5.N_SESSIONS} sessions so far; the verdict waits")
    res = {"session_list": [r["day"] for r in rows], "skipped": skipped, "ITM": fw7a.judge(rows), "changed_vs_fw7b": changed,
           "states": {s: sum(1 for r in rows if (r.get("ITM") or {}).get("state") == s) for s in ("STALE_INDEX", "STALE_BOOK", "NO_SIGNAL", "INADMISSIBLE", "MISSED", "FILLED", "UNRESOLVED")},
           "rows": rows}
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "dev":
        r = session(Path(sys.argv[2]))
        print(json.dumps({k: (v if not isinstance(v, dict) else {x: v.get(x) for x in ("state", "depth", "cap", "quote_age", "latency")})
                          for k, v in r.items() if k not in ("A", "C0", "g")}, default=float))
    elif len(sys.argv) > 1 and sys.argv[1] == "verdict":
        verdict()
    else:
        raise SystemExit("usage: fw7c.py dev FOLDER | verdict")
