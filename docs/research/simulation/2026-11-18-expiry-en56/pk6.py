"""Round 6 packet work (PLAN6.md) on the read-only TR01 export: EN70's recorder minute-bar builder and its parity
against Breeze, EN58's entry policies on real depth, and EN56's library on packets. NIFTY Nov 17 only.

Packets are decoded here (not through round 5b's frozen tr01.extract) because the builder needs the last-trade time
(offset 44). Freshness on every packet used: positive uncrossed top of book, exchange time <= receipt, and an exchange
age <= 2 s at the moment of use."""
from __future__ import annotations
import hashlib, json, lzma, math, sqlite3, struct, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-18-expiry-en41"))
import en_lab6 as L6  # noqa: E402
import tr01  # noqa: E402

L5, L4, E, D4 = L6.L5, L6.L4, L6.E, L6.D4
DAY = "2026-11-17"
EXPORT = tr01.EXPORT
LOCAL = HERE / "_local"
BREEZE = Path.home() / "sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"
IST = 19800
REC = struct.Struct(">qH")
LAT = 1.0                     # seconds, every order and cancellation
FRESH = 2.0                   # seconds of exchange age at use


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def catalogue(day=DAY):
    return tr01.instruments(day)


def tokens(day=DAY):
    cat = catalogue(day)
    idx = next(r["token"] for r in cat if r["type"] == "INDEX" and r["underlying"] == "NIFTY 50")
    futs = sorted([r for r in cat if r["type"] == "FUT" and r["underlying"] == "NIFTY"], key=lambda r: r["expiry"])
    fut = next(r for r in futs if r["expiry"] >= day)
    opts = {(float(r["strike"]), r["type"]): r["token"] for r in cat if r["underlying"] == "NIFTY" and r["type"] in ("CE", "PE") and r["expiry"] == day}
    return idx, fut, opts


def decode(day=DAY):
    """{token: arrays} for NIFTY index, the front future and the expiring chain; cached by token set + this file."""
    idx, fut, opts = tokens(day); want = sorted({idx, fut["token"], *opts.values()})
    key = hashlib.sha256(json.dumps(want).encode()).hexdigest()[:10]
    cache = LOCAL / f"pk6-{day}-{key}-{sha(Path(__file__))[:8]}.npz"
    F = ("recv", "exch", "lt", "ltp", "vol", "oi", "bp", "bq", "ap", "aq")
    if cache.exists():
        z = np.load(cache); return {t: {f: z[f"{t}_{f}"] for f in F} for t in want if f"{t}_recv" in z}
    acc = {t: {f: [] for f in F} for t in want}; ws = set(want)
    p = EXPORT / day; m = json.loads((p / "manifest.json").read_text(encoding="utf-8"))
    names = sorted(c.get("name") or c.get("file") for c in m["chunks"]) if isinstance(m["chunks"], list) else sorted(m["chunks"])
    for name in names:
        raw = lzma.decompress((p / name).read_bytes()); pos = 0; n = len(raw)
        while pos < n:
            recv, length = REC.unpack_from(raw, pos); pos += REC.size
            tok = int.from_bytes(raw[pos:pos + 4], "big")
            if tok in ws:
                pk = raw[pos:pos + length]; a = acc[tok]; dv = 100.
                if tok == idx:
                    if length >= 32:
                        a["recv"].append(recv); a["ltp"].append(struct.unpack_from(">I", pk, 4)[0] / dv); a["exch"].append(struct.unpack_from(">I", pk, 28)[0])
                        a["lt"].append(0); a["vol"].append(0); a["oi"].append(0)
                        a["bp"].append([np.nan] * 5); a["bq"].append([0] * 5); a["ap"].append([np.nan] * 5); a["aq"].append([0] * 5)
                elif length >= 184:
                    a["recv"].append(recv); a["ltp"].append(struct.unpack_from(">I", pk, 4)[0] / dv)
                    a["vol"].append(struct.unpack_from(">I", pk, 16)[0]); a["lt"].append(struct.unpack_from(">I", pk, 44)[0])
                    a["oi"].append(struct.unpack_from(">I", pk, 48)[0]); a["exch"].append(struct.unpack_from(">I", pk, 60)[0])
                    lv = [struct.unpack_from(">IIH", pk, at) for at in range(64, 184, 12)]
                    a["bq"].append([q for q, _, _ in lv[:5]]); a["bp"].append([pr / dv if q else np.nan for q, pr, _ in lv[:5]])
                    a["aq"].append([q for q, _, _ in lv[5:]]); a["ap"].append([pr / dv if q else np.nan for q, pr, _ in lv[5:]])
            pos += length
    out = {}
    for t, a in acc.items():
        if a["recv"]:
            out[t] = dict(recv=np.array(a["recv"], np.int64), exch=np.array(a["exch"], np.int64), lt=np.array(a["lt"], np.int64),
                          ltp=np.array(a["ltp"], float), vol=np.array(a["vol"], np.int64), oi=np.array(a["oi"], np.int64),
                          bp=np.array(a["bp"], float), bq=np.array(a["bq"], np.int64), ap=np.array(a["ap"], float), aq=np.array(a["aq"], np.int64))
    LOCAL.mkdir(exist_ok=True)
    np.savez(cache, **{f"{t}_{f}": v for t, d in out.items() for f, v in d.items()})
    return out


def ist(sec):
    """Unix seconds -> seconds since IST midnight."""
    return (np.asarray(sec, np.int64) + IST) % 86400


# ---------------------------------------------------------------- EN70: minute bars, labelled by bar start
def bars(a, kind):
    """{minute_index k (09:15 = 0): (o, h, l, c, v)}. Index: LTP by exchange time. F&O: LTPs of packets whose cumulative
    volume rose, bucketed by last-trade time; bar volume from the cumulative volume by exchange time."""
    out = {}
    if kind == "index":
        ok = a["exch"] > 0; s = ist(a["exch"][ok]); px = a["ltp"][ok]
        k = (s - 33300) // 60
        for kk in np.unique(k):
            if 0 <= kk < 375:
                w = px[k == kk]; out[int(kk)] = (w[0], w.max(), w.min(), w[-1], 0.)
        return out
    order = np.argsort(a["recv"], kind="stable"); vol = a["vol"][order]; ltp = a["ltp"][order]; lt = a["lt"][order]; ex = a["exch"][order]
    rose = np.r_[False, np.diff(vol) > 0] & (lt > 0)
    s = ist(lt[rose]); px = ltp[rose]; k = (s - 33300) // 60
    se = ist(ex); ke = (se - 33300) // 60
    vend = {}
    for kk in np.unique(ke):
        vend[int(kk)] = int(vol[ke == kk].max())
    prev = None
    for kk in range(0, 375):
        if kk in vend:
            v = vend[kk] - (prev if prev is not None else vend[kk]); prev = vend[kk]
        else:
            v = 0
        w = px[k == kk]
        if len(w):
            out[kk] = (w[0], w.max(), w.min(), w[-1], float(max(v, 0)))
    return out


def breeze_options(day=DAY):
    c = sqlite3.connect(BREEZE.resolve().as_uri() + "?mode=ro", uri=True)
    rows = c.execute("SELECT strike, opt, datetime, open, high, low, close, volume FROM candles WHERE kind='option' AND underlying='NIFTY' "
                     "AND expiry=? AND interval='1minute' AND datetime BETWEEN ? AND ?", (day, day + " 12:00:00", day + " 15:29:00")).fetchall()
    c.close()
    out = {}
    for k_, o, dt, *v in rows:
        kk = (int(dt[11:13]) - 9) * 60 + int(dt[14:16]) - 15
        out[(float(k_), o, kk)] = tuple(float(x) for x in v)
    return out


def parity(day=DAY):
    P = decode(day); idx, fut, opts = tokens(day); B = breeze_options(day)
    strikes = sorted({k for k, _, _ in B}); res = dict(option_bars=0, option_close_ok=0, option_hl_ok=0, option_bars_vol=0,
                                                      option_close_ok_vol=0, breeze_only=0, tr01_only=0, vol_ratio=[])
    for (K, o), tok in opts.items():
        if K not in strikes or tok not in P:
            continue
        b = bars(P[tok], "fo")
        for kk in range(165, 375):
            br = B.get((K, o, kk)); tr = b.get(kk)
            if br and not tr:
                res["breeze_only"] += int(br[4] > 0); continue
            if tr and not br:
                res["tr01_only"] += 1; continue
            if not br:
                continue
            res["option_bars"] += 1; okc = abs(br[3] - tr[3]) <= .10 + 1e-9
            res["option_close_ok"] += okc; res["option_hl_ok"] += (abs(br[1] - tr[1]) <= .10 + 1e-9 and abs(br[2] - tr[2]) <= .10 + 1e-9)
            if br[4] > 0:
                res["option_bars_vol"] += 1; res["option_close_ok_vol"] += okc
                if tr[4] > 0:
                    res["vol_ratio"].append(tr[4] / br[4])
    vr = np.array(res.pop("vol_ratio")) if res.get("vol_ratio") is not None else np.array([])
    res["volume_ratio_median"] = round(float(np.median(vr)), 3) if len(vr) else None
    res["close_ok_share_vol"] = round(res["option_close_ok_vol"] / max(1, res["option_bars_vol"]), 4)
    fb = bars(P[fut["token"]], "fo"); ib = bars(P[idx], "index")
    basis = [fb[k][3] - ib[k][3] for k in range(375) if k in fb and k in ib]
    res.update(future_bars=len(fb), index_bars=len(ib), basis_sd=round(float(np.std(basis)), 3), basis_mean=round(float(np.mean(basis)), 2),
               future_independent_source=False, index_independent_source=False, strikes=len(strikes))
    return res


def write_sqlite(day, use_breeze_options):
    """A scratch candles table in exam2026.sqlite's schema: recorder index + front future, options from the recorder
    (or from Breeze), the Breeze strike set, options 12:00-15:29."""
    P = decode(day); idx, fut, opts = tokens(day); B = breeze_options(day); strikes = sorted({k for k, _, _ in B})
    con = sqlite3.connect(":memory:"); con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE candles(kind TEXT,underlying TEXT,expiry TEXT,strike REAL,opt TEXT,datetime TEXT,open REAL,high REAL,low REAL,"
                "close REAL,volume REAL,oi REAL)")

    def stamp(kk):
        m = 555 + kk; return f"{day} {m // 60:02d}:{m % 60:02d}:00"
    for kk, (o, h, l, c, v) in bars(P[idx], "index").items():
        con.execute("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ("index", "NIFTY", None, None, None, stamp(kk), o, h, l, c, 0, None))
    for kk, (o, h, l, c, v) in bars(P[fut["token"]], "fo").items():
        con.execute("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ("future", "NIFTY", fut["expiry"], None, None, stamp(kk), o, h, l, c, v, None))
    for (K, o_), tok in opts.items():
        if K not in strikes:
            continue
        src = {kk: B[(K, o_, kk)] for kk in range(165, 375) if (K, o_, kk) in B} if use_breeze_options else \
            {kk: v for kk, v in bars(P[tok], "fo").items() if kk >= 165}
        for kk, (o, h, l, c, v) in src.items():
            con.execute("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ("option", "NIFTY", day, K, o_, stamp(kk), o, h, l, c, v, None))
    return con


def tape(day=DAY, use_breeze_options=False):
    con = write_sqlite(day, use_breeze_options); t = D4.build(con, "NIFTY", day, D4._D()); con.close()
    return t


def decision_parity(day=DAY):
    """E03.2 and EN55 on the recorder tape and on the Breeze-options hybrid: decisions, contracts and lots."""
    out = {}
    T1, T2 = tape(day, False), tape(day, True)
    L6.KEEP6.extend([T1, T2])
    for name in ("E032_30k", "EN55"):
        rule = L6.ARMS[name]; got = []
        for t in (T1, T2):
            L6.LOG_INTENTS = []
            L6.run_day6(t, rule, "ordinary", 30000., L6.budget_of(rule), details=True)
            got.append([(x["i"], x["d"], str(t.symbols[x["j"]]).split("-", 2)[-1], x["lots"]) for x in L6.LOG_INTENTS])
            L6.LOG_INTENTS = None
        out[name] = dict(recorder=got[0], hybrid=got[1], same=got[0] == got[1])
    return out, T1, T2


# ---------------------------------------------------------------- packet helpers with freshness
class Book:
    """One instrument's packets in receipt order, with freshness-checked lookups."""

    def __init__(self, a):
        o = np.argsort(a["recv"], kind="stable"); self.a = {k: v[o] for k, v in a.items()}
        self.s = (self.a["recv"] + IST * 10 ** 9) % (86400 * 10 ** 9) / 1e9          # receipt, seconds since IST midnight
        self.e = ist(self.a["exch"]).astype(float)

    def at(self, s):
        """Index of the latest packet received at or before s whose exchange age at s is <= FRESH and whose top of book
        is valid (uncrossed, positive); None otherwise."""
        k = int(np.searchsorted(self.s, s, side="right")) - 1
        while k >= 0 and self.s[k] > s - 30:
            bp, ap, bq, aq = self.a["bp"][k, 0], self.a["ap"][k, 0], self.a["bq"][k, 0], self.a["aq"][k, 0]
            if self.e[k] <= self.s[k] + 1e-6 and s - self.e[k] <= FRESH and np.isfinite([bp, ap]).all() and 0 < bp < ap and bq > 0 and aq > 0:
                return k
            k -= 1
        return None

    def after(self, s, until):
        """Indices of valid fresh packets received in (s, until]."""
        lo, hi = int(np.searchsorted(self.s, s, side="right")), int(np.searchsorted(self.s, until, side="right"))
        for k in range(lo, hi):
            bp, ap, bq, aq = self.a["bp"][k, 0], self.a["ap"][k, 0], self.a["bq"][k, 0], self.a["aq"][k, 0]
            if self.e[k] <= self.s[k] + 1e-6 and self.s[k] - self.e[k] <= FRESH and np.isfinite([bp, ap]).all() and 0 < bp < ap and bq > 0 and aq > 0:
                yield k

    def mid(self, k):
        return (self.a["bp"][k, 0] + self.a["ap"][k, 0]) / 2

    def micro(self, k):
        b, a, qb, qa = self.a["bp"][k, 0], self.a["ap"][k, 0], self.a["bq"][k, 0], self.a["aq"][k, 0]
        return (a * qb + b * qa) / (qb + qa)

    def walk(self, k, side, units, limit):
        """Average price for `units` walking the book at packet k within the limit, or None."""
        px, qx = (self.a["ap"][k], self.a["aq"][k]) if side == "BUY" else (self.a["bp"][k], self.a["bq"][k])
        left, cost = units, 0.
        for p_, q_ in zip(px, qx):
            if not np.isfinite(p_) or q_ <= 0 or (side == "BUY" and p_ > limit + 1e-9) or (side == "SELL" and p_ < limit - 1e-9):
                break
            take = min(left, int(q_)); cost += take * p_; left -= take
            if left == 0:
                return cost / units
        return None


def market(bk, s, side, units, limit, horizon=20.):
    """Marketable order sent at s: the first valid fresh packet received after s + LAT that fills it whole, to s + 20 s."""
    for k in bk.after(s + LAT, s + LAT + horizon):
        p = bk.walk(k, side, units, limit)
        if p is not None:
            return bk.s[k], p
    return None


def rest(bk, s, P, units, until, rule="through"):
    """A resting buy at P placed at s (live from s + LAT): fill time under the price-through proxy (a later best ask
    <= P, or an LTP <= P - 0.05) or the volume-at-bid proxy (cumulative volume at packets with LTP <= P reaching the
    displayed bid quantity at placement + our units). None if unfilled by `until`."""
    k0 = bk.at(s)
    if k0 is None:
        return None
    q0 = int(bk.a["bq"][k0, 0]) if abs(bk.a["bp"][k0, 0] - P) < 1e-9 else 0; v0 = int(bk.a["vol"][k0]); seen = 0
    prev_v = v0
    for k in bk.after(s + LAT, until):
        if rule == "through":
            if bk.a["ap"][k, 0] <= P + 1e-9 or bk.a["ltp"][k] <= P - .05 + 1e-9:
                return bk.s[k]
        else:
            dv = int(bk.a["vol"][k]) - prev_v; prev_v = int(bk.a["vol"][k])
            if dv > 0 and bk.a["ltp"][k] <= P + 1e-9:
                seen += dv
                if seen >= q0 + units:
                    return bk.s[k]
    return None


def fees_nfo(price_, units, buy):
    return L4.fee(L4.NIFTY, price_, units, buy)


# ---------------------------------------------------------------- EN58: entry policies on real depth
POLICIES = ("P0", "P1", "P2", "P3")


def _fmid(fb, s):
    k = fb.at(s)
    return fb.mid(k) if k is not None else math.nan


def _idx(ib, s):
    k = int(np.searchsorted(ib.s, s, side="right")) - 1
    return float(ib.a["ltp"][k]) if k >= 0 and s - ib.e[k] <= FRESH else math.nan


def _passive(ob, s, B0, units, until, proxy, adv_winner):
    """Fill time of a resting bid under the named proxy; 'adversarial' fills ambiguous losers and not ambiguous winners."""
    if proxy in ("through", "volume"):
        return rest(ob, s, B0, units, until, proxy)
    a, b = rest(ob, s, B0, units, until, "through"), rest(ob, s, B0, units, until, "volume")
    if (a is None) == (b is None):
        return a if a is None else min(a, b)
    return None if adv_winner else (a if a is not None else b)


def policy(ob, fb, ib, s, d, units, limit, atr0, ustop, pol, proxy="through"):
    """One entry intent at decision time s (seconds since IST midnight). Returns dict(filled, t, price, how)."""
    k0 = ob.at(s)
    if k0 is None:
        return dict(filled=False, how="STALE_QUOTE")
    B0, A0 = float(ob.a["bp"][k0, 0]), float(ob.a["ap"][k0, 0]); mid0 = (A0 + B0) / 2
    k180 = ob.at(s + 180); adv_win = (k180 is not None and ob.mid(k180) > B0)
    intact = lambda tt: np.isfinite(_idx(ib, tt)) and d * (_idx(ib, tt) - ustop) > 0
    if pol == "P3":
        f0, f10 = _fmid(fb, s), _fmid(fb, s - 10)
        go = np.isfinite([f0, f10]).all() and d * (f0 - f10) > 0 and ob.micro(k0) > mid0
        pol = "P1" if go else "P3w"
    if pol == "P1":
        m = market(ob, s, "BUY", units, limit)
        return dict(filled=m is not None, t=m[0] if m else None, price=m[1] if m else None, how="MARKET")
    wait = 60. if pol == "P0" else 3.
    end = s + LAT + wait
    if pol == "P3w":                                            # early cancel on an adverse 0.10 ATR future move
        f0 = _fmid(fb, s)
        for k in fb.after(s + LAT, end):
            if np.isfinite(f0) and d * (fb.mid(k) - f0) <= -.10 * atr0:
                end = fb.s[k]; break
    tf = _passive(ob, s, B0, units, end + LAT, proxy, adv_win)    # fills during the cancel acknowledgement count
    if tf is not None:
        return dict(filled=True, t=tf, price=B0, how="PASSIVE" if tf <= end else "PASSIVE_RACE")
    s_fb = end + LAT
    if pol == "P0":
        ok = np.isfinite([_fmid(fb, s_fb), _fmid(fb, s)]).all() and d * (_fmid(fb, s_fb) - _fmid(fb, s)) > 0
    else:
        ok = np.isfinite([_fmid(fb, s_fb), _fmid(fb, s_fb - 10)]).all() and d * (_fmid(fb, s_fb) - _fmid(fb, s_fb - 10)) > 0
    if not (ok and intact(s_fb)):
        return dict(filled=False, how="MISSED")
    m = market(ob, s_fb, "BUY", units, limit)
    return dict(filled=m is not None, t=m[0] if m else None, price=m[1] if m else None, how="FALLBACK" if m else "MISSED")


def outcome(ob, s, units, r, hold=480.):
    """Markouts and the P&L to a fixed exit (EN55's 8 minutes), sold into walked bids."""
    k0 = ob.at(s); mid0 = ob.mid(k0) if k0 is not None else math.nan; A0 = float(ob.a["ap"][k0, 0]) if k0 is not None else math.nan
    mk = {}
    for h in (10, 60, 180):
        k = ob.at(s + h); mk[f"mid{h}"] = (ob.mid(k) - mid0) / mid0 if k is not None and np.isfinite(mid0) else math.nan
    out = dict(r, **mk)
    if r.get("filled"):
        p = r["price"]; out["cost_vs_mid"] = (p - mid0) / mid0
        for h in (60, 180):
            k = ob.at(r["t"] + h); out[f"fill{h}"] = (float(ob.a["bp"][k, 0]) - p) / p if k is not None else math.nan
        sale = market(ob, s + hold, "SELL", units, .05)
        if sale:
            out["net"] = round((sale[1] - p) * units - fees_nfo(p, units, True) - fees_nfo(sale[1], units, False), 2)
        else:
            out["net"] = round(-p * units - fees_nfo(p, units, True), 2); out["unresolved"] = 1
    else:
        k = ob.at(s + 180); out["missed_winner"] = max(0., (ob.mid(k) - A0) / A0) if k is not None and np.isfinite(A0) else math.nan
        out["net"] = 0.
    return out


def en58(T1, P):
    """EN55's intents on the recorder tape (primary) and the 5-minute mechanics grid (diagnostic), four policies,
    three passive proxies."""
    idx, fut, opts = tokens(); ib, fb = Book(P[idx]), Book(P[fut["token"]])
    books_ = {k: Book(P[v]) for k, v in opts.items() if v in P}
    L6.LOG_INTENTS = []
    L6.run_day6(T1, L6.ARMS["EN55"], "ordinary", 30000., L6.budget_of(L6.ARMS["EN55"]), details=True)
    intents = L6.LOG_INTENTS; L6.LOG_INTENTS = None
    rows = []

    def run(tag, s, d, K, kind, units, limit, atr0, ustop):
        ob = books_.get((K, kind))
        if ob is None:
            return
        for pol in POLICIES:
            for proxy in ("through", "volume", "adversarial"):
                if pol == "P1" and proxy != "through":
                    continue
                r = policy(ob, fb, ib, s, d, units, limit, atr0, ustop, pol, proxy)
                rows.append(dict(outcome(ob, s, units, r), tag=tag, s=s, d=d, K=K, kind=kind, units=units, policy=pol, proxy=proxy))
    for x in intents:
        i, d, j = x["i"], x["d"], x["j"]; s = float(T1.minute[i]) * 60; K = float(T1.strikes[j]); kind = "CE" if T1.kinds[j] == 1 else "PE"
        a0 = float(T1.features[10][i, 4]); ob = books_.get((K, kind)); k0 = ob.at(s) if ob else None
        units = x["lots"] * L4.NIFTY.lot
        wa = ob.walk(k0, "BUY", units, 1e9) if k0 is not None else None
        limit = min(x["limit"], E.down(1.04 * wa)) if wa else x["limit"]
        run("EN55", s, d, K, kind, units, limit, a0, float(T1.close[i]) - d * 2 * a0)
    for m in range(780, 901, 5):
        i = L6.at(T1, m)
        if i >= T1.n or T1.minute[i] != m:
            continue
        s = m * 60.; c = float(T1.close[i]); a0 = float(T1.features[10][i, 4])
        for d in (1, -1):
            kind = "CE" if d > 0 else "PE"
            cand = sorted([K for (K, kd) in books_ if kd == kind and d * (K - c) > 0], key=lambda K: d * K)
            for K in cand:
                ob = books_[(K, kind)]; k0 = ob.at(s)
                if k0 is None or not 5 <= ob.a["ap"][k0, 0] <= 20:
                    continue
                run("GRID", s, d, K, kind, L4.NIFTY.lot, E.down(1.04 * float(ob.a["ap"][k0, 0])), a0, c - d * 2 * a0)
                break
    return intents, rows


# ---------------------------------------------------------------- EN56 on packets
def en56_packets(T1, P):
    """The EN56 library rows on the recorder minute tape (bar proxy) beside the same rows filled on recorder depth."""
    idx, fut, opts = tokens(); books_ = {k: Book(P[v]) for k, v in opts.items() if v in P}
    rows = L6.library(T1); out = []
    for r in rows:
        x = dict(zip(L6.LIBF, r))
        if x["status"] != L6.ST["FILLED"]:
            continue
        K = float(T1.strikes[x["j"]]); kind = "CE" if T1.kinds[x["j"]] == 1 else "PE"; ob = books_.get((K, kind))
        s = float(T1.minute[x["i"]]) * 60; units = x["lots"] * L4.NIFTY.lot
        k0 = ob.at(s) if ob else None
        wa = ob.walk(k0, "BUY", units, 1e9) if k0 is not None else None
        pk = dict(net=None)
        if wa:
            b = market(ob, s, "BUY", units, E.down(1.04 * wa))
            if b:
                h_end = min(s + 60 * x["h"], 914 * 60.)
                sl = market(ob, max(h_end, b[0]), "SELL", units, .05)
                if sl:
                    pk = dict(net=round((sl[1] - b[1]) * units - fees_nfo(b[1], units, True) - fees_nfo(sl[1], units, False), 2))
                else:
                    pk = dict(net=round(-b[1] * units - fees_nfo(b[1], units, True), 2), unresolved=1)
            else:
                pk = dict(net=0., nofill=1)
        out.append(dict(m=x["m"], d=x["d"], off=x["off"], R=x["R"], h=x["h"], bar_net=x["net"], **{f"pk_{k}": v for k, v in pk.items()}))
    return out
