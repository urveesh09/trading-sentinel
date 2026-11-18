"""Round-9 causal features and event builders (IMPL9.md section 3). Read-only on round-8 frames.

Every array for a session reads only that session's completed bars up to the decision minute and earlier
covered sessions' window minutes. Thresholds never read the current or later sessions.
"""
from dataclasses import replace
import math
import numpy as np
import round8  # noqa: F401  (path setup + network guard)
from data8 import L7, basket as basket8
import signals8
L4, L3 = L7.L4, L7.L3
E = L7.E
WIN = (780, 870)
LOOKBACKS = (5, 10, 15, 30)
WIDTHS = (1, 2, 3)
ANCHORS = ("CURRENT_ATM", "LAG15_ATM", "FROZEN_1300_ATM")
AGGS = ("POOLED", "MEDIAN_LEAVE_ONE_PAIR_OUT")
REF_REP = (15, 2, "CURRENT_ATM", "POOLED")          # round-8 EN87 representation


def window(t, end=870):
    return (t.minute >= WIN[0]) & (t.minute < end)


def lookup(t):
    if not hasattr(t, "_look9"):
        t._look9 = {(float(K), int(d)): j for j, (K, d) in enumerate(zip(t.strikes, t.kinds))}
    return t._look9


def strict_pairs(t, k, hw):
    """Centered basket at anchor bar k; None when the anchor is invalid or the catalogue lacks a required pair."""
    if k < 0 or k >= t.n or not np.isfinite(t.close[k]):
        return None
    sp = L4.spec_of(t); atm = round(float(t.close[k]) / sp.step) * sp.step; look = lookup(t); out = []
    for off in range(-hw, hw + 1):
        K = atm + off * sp.step
        c, p = look.get((K, 1)), look.get((K, -1))
        if c is None or p is None:
            return None
        out.append((c, p))
    return out


def anchor_of(t, i, anchor):
    if anchor == "CURRENT_ATM":
        return i
    if anchor == "LAG15_ATM":
        return i - 15
    k = int(np.searchsorted(t.minute, 780))
    return k if i >= k else -1                      # frozen 13:00 basket: unavailable before 13:00


def pair_terms(oi, i, L, pairs):
    """[(num, den, |dC|+|dP|)] for pairs with all four endpoints; zero OI is a valid observation."""
    out = []
    for c, p in pairs:
        c0, ct, p0, pt = oi[i - L, c], oi[i, c], oi[i - L, p], oi[i, p]
        if not (np.isfinite(c0) and np.isfinite(ct) and np.isfinite(p0) and np.isfinite(pt)):
            continue
        out.append(((c0 - ct) + (pt - p0), c0 + p0, abs(c0 - ct) + abs(pt - p0)))
    return out


def ref_score(t, i, L, pairs=None):
    """Round-8 components() generalised to lookback L, identical accumulation order (narrower basket allowed, >=3 pairs)."""
    if i < L:
        return math.nan
    oi = t.oi8; pairs = basket8(t, i) if pairs is None else pairs
    den = up = dn = 0.; valid = 0
    for c, p in pairs:
        c0, ct, p0, pt = oi[i - L, c], oi[i, c], oi[i - L, p], oi[i, p]
        if not np.isfinite([c0, ct, p0, pt]).all():
            continue
        den += c0 + p0; up += max(c0 - ct, 0) - max(p0 - pt, 0); dn += max(pt - p0, 0) - max(ct - c0, 0); valid += 1
    if valid < 3 or den <= 0:
        return math.nan
    return up / den + dn / den


def rep_score(t, i, rep, pairs=None):
    """S for a representation (L, half-width, anchor, aggregation). The reference rep uses round-8 semantics."""
    L, hw, anchor, agg = rep
    if rep[1:] == REF_REP[1:]:
        return ref_score(t, i, L, pairs)
    if i < L:
        return math.nan
    if pairs is None:
        pairs = strict_pairs(t, anchor_of(t, i, anchor), hw)
    if pairs is None:
        return math.nan
    terms = pair_terms(t.oi8, i, L, pairs)
    if agg == "POOLED":
        if len(terms) < max(2, math.ceil(.6 * len(pairs))):
            return math.nan
        den = sum(x[1] for x in terms)
        return sum(x[0] for x in terms) / den if den > 0 else math.nan
    if len(terms) < 3:
        return math.nan
    num = sum(x[0] for x in terms); den = sum(x[1] for x in terms); loo = []
    for a, b, _ in terms:
        if den - b > 0:
            loo.append((num - a) / (den - b))
    return float(np.median(loo)) if len(loo) == len(terms) else math.nan


def rep_series(t, rep):
    if rep == REF_REP:
        return t.frame8["components"][:, 0]
    out = np.full(t.n, np.nan)
    for i in range(rep[0], t.n):
        out[i] = rep_score(t, i, rep)
    return out


def rep_diagnostics(t, rep, i):
    L, hw, anchor, agg = rep
    pairs = basket8(t, i) if rep[1:] == REF_REP[1:] else strict_pairs(t, anchor_of(t, i, anchor), hw)
    if pairs is None or i < L:
        return dict(valid_pairs=0, planned=2 * hw + 1)
    terms = pair_terms(t.oi8, i, L, pairs); tot = sum(x[2] for x in terms)
    atm_now = strict_pairs(t, i, 0); atm_lag = strict_pairs(t, i - 15, 0)
    return dict(valid_pairs=len(terms), planned=2 * hw + 1, denominator=float(sum(x[1] for x in terms)),
                largest_share=float(max((x[2] for x in terms), default=0) / tot) if tot > 0 else None,
                atm_changed=bool(atm_now and atm_lag and atm_now[0] != atm_lag[0]))


class Threshold:
    """q(p, H) from the prior H covered sessions' 13:00-14:29 |x| (pooled minutes, >=200 valid), never the current day."""

    def __init__(self, H, p):
        self.H, self.p, self.hist = H, p, []

    def value(self):
        if len(self.hist) < self.H:
            return math.nan
        x = np.concatenate(self.hist[-self.H:]); x = x[np.isfinite(x)]
        return float(np.percentile(np.abs(x), self.p)) if len(x) >= 200 else math.nan

    def update(self, t, series):
        w = window(t); v = series[w]
        if np.mean(np.isfinite(v)) >= .95:
            self.hist.append(v.copy())
            return True
        return False


def er10(t, i):
    F = t.f[:, 3]
    if i < 10:
        return math.nan
    w = F[i - 10:i + 1]
    if not np.isfinite(w).all():
        return math.nan
    den = float(np.abs(np.diff(w)).sum())
    return abs(float(w[-1] - w[0])) / den if den > 0 else math.nan


def extension(t, i, d):
    F = t.f[:, 3]; A = t.features[10][i, 4]
    if i < 15 or not np.isfinite([F[i], F[i - 15], A]).all() or A <= 0:
        return math.nan
    return d * float(F[i] - F[i - 15]) / float(A)


def basis_innovation(t):
    """e_i = (F - index)_i minus the median of the prior 60 minutes (>=40 valid). SENSEX needs a fresh futures bar."""
    X = t.close.astype(float); F = t.f[:, 3]; b = F - X; e = np.full(t.n, np.nan)
    fresh = None
    if getattr(t, "und", "NIFTY") == "SENSEX":
        fv = L3.futvol(t); fresh = np.isfinite(fv) & (fv > 0)
    for i in range(60, t.n):
        w = b[i - 60:i]; w = w[np.isfinite(w)]
        if len(w) >= 40 and np.isfinite(b[i]) and (fresh is None or fresh[i]):
            e[i] = b[i] - float(np.median(w))
    return e


def syn_score(t):
    s = t.frame8["innovation"].copy()
    if getattr(t, "und", "NIFTY") == "SENSEX":
        fv = L3.futvol(t); s[~(np.isfinite(fv) & (fv > 0))] = np.nan
    return s


def e03_dirs(t, rule):
    return L7.signals7(t, rule)[0].astype(np.int8)


# ------------------------------------------------------------------ event builders
def gate(edirs, S, q, win, mode="GATE"):
    """GATE: d*S>q; VETO: drop only when d*S<-q (missing keeps); returns int8 directions."""
    out = np.zeros(len(edirs), np.int8)
    for i in np.flatnonzero((edirs != 0) & win):
        d = int(edirs[i]); s = S[i]
        if mode == "GATE":
            if np.isfinite(q) and np.isfinite(s) and d * s > q:
                out[i] = d
        elif mode == "VETO":
            if not (np.isfinite(q) and np.isfinite(s) and d * s < -q):
                out[i] = d
        else:
            raise ValueError(mode)
    return out


def context(t, ev, maxX, minER):
    """EN98: keep events with valid features, X <= maxX (None = unbounded) and ER10 >= minER."""
    out = np.zeros(t.n, np.int8); logs = []
    for i in np.flatnonzero(ev):
        d = int(ev[i]); x = extension(t, int(i), d); er = er10(t, int(i))
        ok = np.isfinite(x) and np.isfinite(er) and (maxX is None or x <= maxX) and er >= minER
        if ok:
            out[i] = d
        logs.append(dict(i=int(i), d=d, X=None if not np.isfinite(x) else round(x, 4), ER10=None if not np.isfinite(er) else round(er, 4), kept=bool(ok)))
    return out, logs


def reversed_context(t, ev, minX):
    out = np.zeros(t.n, np.int8)
    for i in np.flatnonzero(ev):
        d = int(ev[i]); x = extension(t, int(i), d)
        if np.isfinite(x) and x > minX:
            out[i] = d
    return out


def nominal_pick(t, i, d, rule, chooser=None):
    sp = L4.spec_of(t)
    if chooser is not None:
        return chooser(sp, t, int(i), d, rule, 2500., 30000.)
    return L4.choose4(sp, t, int(i), d, rule, 2500., 30000.)


def arms99(t, ev, S, q, style, ttl, amount, ceil, rule, chooser=None):
    """EN99 bar entry arms from qualified events. Returns (dirs at trigger bars, picks, logs). One active arm."""
    out = np.zeros(t.n, np.int8); picks = {}; logs = []; busy = -1
    F, FH, FL = t.f[:, 3], t.f[:, 1], t.f[:, 2]
    for i in np.flatnonzero(ev):
        i = int(i); d = int(ev[i])
        if i <= busy:
            logs.append(dict(event_i=i, d=d, status="ARM_ACTIVE")); continue
        A = float(t.features[10][i, 4])
        if not np.isfinite(A) or A <= 0 or not np.isfinite(F[i]):
            logs.append(dict(event_i=i, d=d, status="INVALID_ARM_INPUT")); continue
        pick = nominal_pick(t, i, d, rule, chooser)
        if pick is None:
            logs.append(dict(event_i=i, d=d, status="UNAFFORDABLE_AT_EVENT")); continue
        j = int(pick[0]); ask0 = float(L4.ask_of(t.q[i, j, 3])); ext = d * float(F[i]); pulled = False
        why = "TTL_EXPIRED"; trig = None; last = i
        for b in range(i + 1, min(i + ttl + 1, t.n)):
            last = b
            if t.minute[b] >= 870:
                why = "WINDOW_END"; break
            s = S[b]
            if not (np.isfinite(s) and np.isfinite(q)) or d * s <= q:
                why = "INFORMATION_LOST"; break
            if not np.isfinite(F[b]) or not np.isfinite(t.q[b, j]).all():
                why = "MISSING_INPUT"; break
            ask = float(L4.ask_of(t.q[b, j, 3]))
            if style == "CONFIRM":
                ok = d * (F[b] - F[i]) >= amount * A
            else:
                ext = max(ext, d * float(F[b])); pulled = pulled or ext - d * float(F[b]) >= amount * A
                prev = FH[b - 1] if d > 0 else FL[b - 1]
                ok = pulled and np.isfinite(prev) and d * (F[b] - prev) > 0
            if ok and ask <= ceil * ask0 + 1e-9:
                trig = b; why = "TRIGGER"; break
        busy = last
        log = dict(event_i=i, d=d, j=j, ask0=ask0, atr=A, status=why, end_i=last)
        if trig is not None:
            out[trig] = d; picks[trig] = dict(j=j, ask0=ask0, ceil=ceil, event_i=i); log["i"] = trig
        logs.append(log)
    return out, picks, logs


def delayed_control(t, ev, ttl, rule):
    """EN99 deterministic-delay control: submit at event+ttl, frozen contract, ceiling 1.08, no information."""
    out = np.zeros(t.n, np.int8); picks = {}; busy = -1
    for i in np.flatnonzero(ev):
        i = int(i); d = int(ev[i]); b = i + ttl
        if i <= busy or b >= t.n or t.minute[b] >= 870:
            continue
        pick = nominal_pick(t, i, d, rule)
        if pick is None:
            continue
        j = int(pick[0]); busy = b
        out[b] = d; picks[b] = dict(j=j, ask0=float(L4.ask_of(t.q[i, j, 3])), ceil=1.08, event_i=i)
    return out, picks


def arms104(t, edirs, S, q_core, q_delay, ttl, validity, rule, unconditional=False):
    """EN104: EN87 core events plus delayed arms from E03 events whose valid OI failed the immediate gate."""
    win = window(t); core = gate(edirs, S, q_core, win)
    out = core.copy(); picks = {}; logs = []; busy = -1
    F, FH, FL = t.f[:, 3], t.f[:, 1], t.f[:, 2]
    for i in np.flatnonzero((edirs != 0) & win):
        i = int(i); d = int(edirs[i])
        if core[i]:
            continue
        if not (np.isfinite(S[i]) and np.isfinite(q_core)):
            logs.append(dict(event_i=i, d=d, status="SOURCE_OR_WARMUP_UNAVAILABLE")); continue
        if i <= busy:
            logs.append(dict(event_i=i, d=d, status="ARM_ACTIVE")); continue
        pick = nominal_pick(t, i, d, rule)
        if pick is None or i < 3:
            logs.append(dict(event_i=i, d=d, status="UNAFFORDABLE_AT_EVENT")); continue
        j = int(pick[0]); ask0 = float(L4.ask_of(t.q[i, j, 3]))
        ref = float(np.min(FL[i - 3:i]) if d > 0 else np.max(FH[i - 3:i]))
        why = "TTL_EXPIRED"; trig = None; last = i
        for b in range(i + 1, min(i + ttl + 1, t.n)):
            last = b
            if t.minute[b] >= 870:
                why = "WINDOW_END"; break
            if core[b]:
                why = "IMMEDIATE_PRIORITY"; break
            if edirs[b] == -d:
                why = "OPPOSITE_E03"; break
            if not np.isfinite(t.q[b, j]).all():
                why = "MISSING_INPUT"; break
            ask = float(L4.ask_of(t.q[b, j, 3]))
            if unconditional:
                if b == i + ttl and ask <= 1.08 * ask0 + 1e-9:
                    trig = b; why = "TRIGGER"
                continue
            if not (np.isfinite(S[b]) and np.isfinite(q_delay) and np.isfinite(F[b]) and np.isfinite(ref)):
                why = "MISSING_INPUT"; break
            if validity == "STRUCTURE_HOLDS" and d * (F[b] - ref) < 0:
                why = "STRUCTURE_BROKEN"; break
            valid = edirs[b] == d if validity == "E03_STILL_SAME" else True
            if valid and d * S[b] > q_delay and ask <= 1.08 * ask0 + 1e-9:
                trig = b; why = "TRIGGER"; break
        busy = last
        log = dict(event_i=i, d=d, j=j, ask0=ask0, status=why, end_i=last)
        if trig is not None:
            out[trig] = d; picks[trig] = dict(j=j, ask0=ask0, ceil=1.08, event_i=i); log["i"] = trig
        logs.append(log)
    return out, picks, logs


def graded_caps(edirs, S, q, win, s1, s2, zhi, s3=3):
    """EN109: lots cap by z=d*S/q: z<0 -> 0, [0,1) -> s1, [1,zhi) -> s2, >=zhi -> s3; missing -> 0."""
    out = np.zeros(len(edirs), np.int8); caps = {}
    for i in np.flatnonzero((edirs != 0) & win):
        d = int(edirs[i]); s = S[i]
        if not (np.isfinite(s) and np.isfinite(q) and q > 0):
            continue
        z = d * s / q
        cap = 0 if z < 0 else s1 if z < 1 else s2 if z < zhi else s3
        if cap > 0:
            out[i] = d; caps[int(i)] = dict(max_lots=int(cap), z=round(float(z), 4))
    return out, caps


def tilt_caps(edirs, S, q, win):
    """EN106 TILT: every native signal kept; agree (d*S>q) keeps native size, otherwise one lot."""
    out = np.zeros(len(edirs), np.int8); caps = {}
    for i in np.flatnonzero((edirs != 0) & win):
        d = int(edirs[i]); s = S[i]; out[i] = d
        agree = np.isfinite(s) and np.isfinite(q) and d * s > q
        if not agree:
            caps[int(i)] = dict(max_lots=1)
    return out, caps
