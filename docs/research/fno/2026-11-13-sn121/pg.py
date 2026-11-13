"""SN121-SN130 helpers. Imports the SN92 harness (Gold v5 parity proven), phase A's quote-archive loader and SN95's
admission flags; edits nothing. Partner data: the frozen Nov 4 Production extract, SHA-256 checked, read only;
nothing derived from it in rupee totals is ever written to a committed file."""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "_local"
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn101"))
import pa  # noqa: E402
import qa  # noqa: E402

C, M, L = pa.C, pa.M, pa.C.L
PARTNER = M.ROOT / "docs/research/partner/2026-11-04-assistance-review"
NOTIONAL = 25000.0


# ---------------------------------------------------------------------------------------------------------------
# partner extract

def partner_trips():
    b = (PARTNER / "_local" / "production-selected.json").read_bytes()
    want = json.loads((PARTNER / "input-manifest.json").read_text(encoding="utf-8"))["sha256"]
    assert hashlib.sha256(b).hexdigest() == want, "partner extract hash mismatch"
    trips = json.loads(b)["tables"]["partner_watch_trips"]
    return sorted(trips, key=lambda t: t["first_at"])


def ist_minute(ts):
    if not ts:
        return None
    t = dt.datetime.fromisoformat(ts)
    return t.hour * 60 + t.minute - 555


def symbol_map(day):
    """tradingsymbol -> (underlying, expiry, strike, CE/PE) from that day's archived quotes (hash-checked)."""
    LOCAL.mkdir(exist_ok=True)
    p = LOCAL / f"symbols-{day}.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    m = qa.manifest()["files_sha256"]
    out = {}
    for k in m:
        if k.startswith(f"quotes/{day}/") and k.endswith(".jsonl.gz"):
            raw = (qa.EXPORT / k).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == m[k]
            for line in gzip.decompress(raw).decode("utf-8").splitlines():
                c = json.loads(line)["contract"]
                if c["instrument_type"] in ("CE", "PE"):
                    out[c["tradingsymbol"]] = (c["underlying"], c["expiry"], int(round(float(c["strike"]))), c["instrument_type"])
    p.write_bytes(pickle.dumps(out))
    return out


def qmid(rec, i):
    if rec is None or not (0 <= i < qa.NM) or not rec["usable"][i] or np.isnan(rec["bid"][i]) or np.isnan(rec["ask"][i]):
        return None
    return float((rec["bid"][i] + rec["ask"][i]) / 2)


def qbid(rec, i):
    if rec is None or not (0 <= i < qa.NM) or not rec["usable"][i] or np.isnan(rec["bid"][i]):
        return None
    return float(rec["bid"][i])


def qask(rec, i):
    if rec is None or not (0 <= i < qa.NM) or not rec["usable"][i] or np.isnan(rec["ask"][i]):
        return None
    return float(rec["ask"][i])


# ---------------------------------------------------------------------------------------------------------------
# minute-cache option prices with a 5-minute freshness guard

def mark(S, strike, opt, j, stale=5):
    rec = S.option(strike, opt)
    if rec is None:
        return None
    col = rec[0][3][: j + 1]
    ok = np.flatnonzero(~np.isnan(col))
    if not len(ok) or j - ok[-1] > stale:
        return None
    return float(col[ok[-1]])


def structure_open(S, i, legs):
    """legs: [(strike, opt, +1 long / -1 short)]; returns [(strike, opt, side, fill)] at minute i or None.
    Longs pay the ask, shorts receive the bid; every leg must have printed at minute i."""
    out = []
    for k, o, s in legs:
        rec = S.option(k, o)
        if rec is None or not rec[6][i]:
            return None
        px = float(rec[0][3][i])
        out.append((k, o, s, M.ask_of(px) if s > 0 else M.bid_of(px)))
    return out


def structure_close(S2, j, opened, leg_stress):
    """Net of closing every leg at minute j of session S2 (longs sold at the bid, shorts bought at the ask), with
    charges on each leg's round trip and the stress per leg; None when a leg has no fresh price."""
    net = 0.0
    for k, o, s, fill in opened:
        m = mark(S2, k, o, j)
        if m is None:
            return None
        if s > 0:
            x = M.bid_of(m)
            net += (x - fill) * M.LOT - M.charges(fill, x, M.LOT)
        else:
            x = M.ask_of(m)
            net += (fill - x) * M.LOT - M.charges(x, fill, M.LOT)
    return net - leg_stress * len(opened)


def credit(opened):
    return sum(-s * fill for _k, _o, s, fill in opened)


def fly(K, w=200):
    return [(K, "CE", -1), (K, "PE", -1), (K + w, "CE", +1), (K - w, "PE", +1)]


def condor(K, inner=50, outer=250):
    return [(K + inner, "CE", -1), (K - inner, "PE", -1), (K + outer, "CE", +1), (K - outer, "PE", +1)]


def max_loss(opened, legs_kind):
    """Defined maximum loss per lot of a fly / condor: wing width minus the credit."""
    width = 200 if legs_kind == "fly" else 200
    return (width - credit(opened)) * M.LOT


def all_sessions():
    Ys = C.years()
    return [S for y in C.YEARS for S in Ys[y].ordered()]


def next_trading_day(day):
    k = C.bisect.bisect_right(C._CAL, day)
    return C._CAL[k] if k < len(C._CAL) else None
