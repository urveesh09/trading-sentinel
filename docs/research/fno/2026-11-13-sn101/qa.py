"""Production quote archive (forward panel export 20261112T103005Z), read in place, read-only, every file checked
against the export manifest's SHA-256. One compact pickle per day in _local/ (git-ignored).

Per day: {"fut": {(underlying, expiry): rec}, "opt": {(underlying, expiry, strike, opt): rec}, "lot": {underlying: lot}}, rec =
dict of arrays over minutes 0..385 (09:15 .. 15:40, the last snapshot inside each minute):
  bid, ask (best), bq, aq (best quantities), bidp / askp / bidq / askq (5 x levels), ltp, vol, oi, age (seconds between
  the provider timestamp and our receipt), usable (depth state USABLE and not crossed / locked)."""
from __future__ import annotations

import gzip
import hashlib
import json
import pickle
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "_local"
EXPORT = Path(r"C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel"
              r"\_local\exports\20261112T103005Z")
NM = 386


def manifest():
    return json.loads((EXPORT / "manifest.json").read_text(encoding="utf-8"))


def days():
    m = manifest()
    return [d for d in m["quote_days"] if d not in set(m["unsealed_days"])]


def _minute(raw):
    return int(raw[11:13]) * 60 + int(raw[14:16]) - 555


def _iso_s(t):
    # "2026-10-29T03:45:29Z" or with fraction / offset -> seconds of day (UTC)
    t = t.replace("Z", "")
    hh, mm, ss = t[11:13], t[14:16], t[17:]
    ss = ss.split("+")[0]
    return int(hh) * 3600 + int(mm) * 60 + float(ss)


def _new():
    z = lambda: np.full(NM, np.nan)  # noqa: E731
    return {"bid": z(), "ask": z(), "bq": z(), "aq": z(), "ltp": z(), "vol": z(), "oi": z(), "age": z(),
            "usable": np.zeros(NM, bool), "bidp": np.full((5, NM), np.nan), "askp": np.full((5, NM), np.nan),
            "bidq": np.full((5, NM), np.nan), "askq": np.full((5, NM), np.nan)}


def build_day(day):
    m = manifest()["files_sha256"]
    files = [k for k in m if k.startswith(f"quotes/{day}/") and k.endswith(".jsonl.gz")]
    assert files, day
    out = {"fut": {}, "opt": {}, "lot": {}}
    for k in files:
        p = EXPORT / k
        b = p.read_bytes()
        assert hashlib.sha256(b).hexdigest() == m[k], f"hash mismatch {k}"
        for line in gzip.decompress(b).decode("utf-8").splitlines():
            r = json.loads(line)
            c = r["contract"]
            raw = r.get("provider_timestamp_raw")
            if not raw:
                continue
            i = _minute(raw)
            if not 0 <= i < NM:
                continue
            und, typ = c["underlying"], c["instrument_type"]
            out["lot"][und] = int(c["lot_size"])
            if typ == "FUT":
                rec = out["fut"].setdefault((und, c["expiry"]), _new())
            else:
                rec = out["opt"].setdefault((und, c["expiry"], int(round(float(c["strike"]))), typ), _new())
            bd, sd = r.get("buy_depth") or [], r.get("sell_depth") or []
            ok = r.get("depth_state") == "USABLE" and not r.get("crossed_depth") and not r.get("locked_depth")
            rec["usable"][i] = ok
            rec["ltp"][i] = r.get("ltp") if r.get("ltp") is not None else np.nan
            rec["vol"][i] = r.get("volume") if r.get("volume") is not None else np.nan
            rec["oi"][i] = r.get("oi") if r.get("oi") is not None else np.nan
            try:
                rec["age"][i] = (_iso_s(r["received_at_utc"]) - _iso_s(r["provider_timestamp_utc"])) % 86400
            except Exception:
                pass
            for lv in range(5):
                if lv < len(bd) and (bd[lv].get("price") or 0) > 0 and (bd[lv].get("quantity") or 0) > 0:
                    rec["bidp"][lv, i], rec["bidq"][lv, i] = bd[lv]["price"], bd[lv]["quantity"]
                else:
                    rec["bidp"][lv, i] = rec["bidq"][lv, i] = np.nan
                if lv < len(sd) and (sd[lv].get("price") or 0) > 0 and (sd[lv].get("quantity") or 0) > 0:
                    rec["askp"][lv, i], rec["askq"][lv, i] = sd[lv]["price"], sd[lv]["quantity"]
                else:
                    rec["askp"][lv, i] = rec["askq"][lv, i] = np.nan
            rec["bid"][i], rec["ask"][i] = rec["bidp"][0, i], rec["askp"][0, i]
            rec["bq"][i], rec["aq"][i] = rec["bidq"][0, i], rec["askq"][0, i]
    return out


def load(day):
    LOCAL.mkdir(exist_ok=True)
    p = LOCAL / f"quotes-{day}.pkl"
    if not p.exists():
        data = build_day(day)
        tmp = p.with_suffix(".tmp")
        with open(tmp, "wb") as fh:
            pickle.dump(data, fh)
        tmp.replace(p)
    with open(p, "rb") as fh:
        return pickle.load(fh)


def first_at(rec, i0, need_usable=True):
    """First minute >= i0 with a usable two-sided quote."""
    for i in range(i0, NM):
        if (not need_usable or rec["usable"][i]) and not np.isnan(rec["bid"][i]) and not np.isnan(rec["ask"][i]):
            return i
    return None


def last_before(rec, i1, i0=0):
    for i in range(i1, i0 - 1, -1):
        if rec["usable"][i] and not np.isnan(rec["bid"][i]) and not np.isnan(rec["ask"][i]):
            return i
    return None


def walk_cost(prices, qtys, units):
    """Average price paid (or received) for `units` by walking the 5 levels; None when the book is too thin."""
    left, cost = units, 0.0
    for p, q in zip(prices, qtys):
        if np.isnan(p) or np.isnan(q) or left <= 0:
            continue
        take = min(left, q)
        cost += take * p
        left -= take
    return None if left > 0 else cost / units


def front_fut(q, und):
    """The futures record with the most usable minutes that day (one contract, never a blend)."""
    cands = [(int(r["usable"].sum()), k) for k, r in q["fut"].items() if k[0] == und]
    return q["fut"][max(cands)[1]] if cands else None
