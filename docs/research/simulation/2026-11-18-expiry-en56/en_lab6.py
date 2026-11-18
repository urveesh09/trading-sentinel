"""EN56-EN70 lab (PLAN6.md). `run_day6` is a hooked copy of the immutable en_lab4.run_day4; with every round-6 hook
off it reproduces run_day4 day by day (check()). Round 5's dispatchers (en_lab5.install) are reused unchanged; round 6
adds no monkeypatch: its own signals / contract choice / exits are called explicitly from run_day6.

Round-6 Rule fields (all off by default):
  parent_cap   cap on one parent's all-in reserve
  max_intents  cap on submitted entry orders a day
  ladder       '' native exit ladder; 'stop_only' = 35% stop + the slot's own exits + clock + flat
  core_bank    EN65: sell the whole core once its after-fee profit >= its outlay (CORE_BANK)
  core_child   EN65: after a filled CORE_BANK with profit G > 0, one child funded by <= G/2 (<= Rs 500)
  liq_pick     EN63: 'liq' cheapest round-trip friction among ATM / ITM1 / OTM1 (one lot); 'cash' = the native
               contract with the most lots inside the 'liq' reserve (cash-matched diagnostic)
Setups (setup3): CUSUM, CUSUM_ORB5 (EN60); RESID, RESID_DIR, RESID_DECAY (EN62); IMPACT, IMPACT_RET, IMPACT_VOL (EN64).
Perturbations (EN57): extra adverse ticks, one bar of extra delay on marketable fills, passive ambiguity scenarios.
Every day result carries `marked_worst`: the worst intratrade equity (open lots marked at each bar's low bid after sell
charges), computed from the order ledger."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass, asdict, replace
import hashlib, json, math, random, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-18-expiry-en41"))
import en_lab5 as L5  # noqa: E402

L4, L3, M, R, L, X, E, D4 = L5.L4, L5.L3, L5.M, L5.R, L5.L, L5.X, L5.E, L5.D4
PARTIAL = L4.PARTIAL
YM = X.YEAR_MIN
SEED = 20261118
TICK = {"NIFTY": .10, "SENSEX": .05}           # front-future tick, dated catalogue of Nov 17 (a floor that never binds)
und, at, atr, options_at, forward, ivol, price = L5.und, L5.at, L5.atr, L5.options_at, L5.forward, L5.ivol, L5.price


@dataclass(frozen=True)
class Rule(L5.Rule):
    parent_cap: float = 0.
    max_intents: int = 0
    ladder: str = ""
    core_bank: bool = False
    core_child: bool = False
    liq_pick: str = ""

    @property
    def key(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


def R6(rule, **kw):
    return replace(Rule(**asdict(rule)), **kw)


E032 = R6(L5.E032)
EN55 = R6(L5.ARMS["EN55"])
SYM = R6(L5.SYM)
ENV = dict(slots=1, put_mult=1., call_mult=1.)                                   # one Rs 2,500 parent per expiry
NEW6 = dict(ENV, chase=.04, max_intents=3, start=750, end=871, hold=15, underlying_stop=0.)


# ---------------------------------------------------------------- perturbations (EN57)
PERT = dict(ticks=0, delay=0, passive="native")


@contextmanager
def perturb(**kw):
    old = dict(PERT); PERT.update(kw)
    try:
        yield
    finally:
        PERT.clear(); PERT.update(old)


def _exe(sp, t, i, j, side, scenario, lots):
    if PERT["delay"]:
        i += PERT["delay"]
        if i >= t.n:
            return 0, None
    filled, px = L4.executable(sp, t, i, j, side, scenario, lots)
    if filled and PERT["ticks"]:
        px = round(px + PERT["ticks"] * .05, 2) if side == "BUY" else round(px - PERT["ticks"] * .05, 2)
        if px <= 0:
            return 0, None
    return filled, px


def _loses_later(t, j, decision, P):
    """ADVERSARIAL passive stress (look-ahead, stress only): a resting bid fills only if the option is below it 8 bars on."""
    for k in range(min(t.n - 1, decision + 9), decision, -1):
        c = t.q[k, j, 3]
        if np.isfinite(c):
            return bool(c < P)
    return True


# ---------------------------------------------------------------- shared series
_C = {}


def fz(t):
    """EN60's z per completed future minute: log return / max(sd of the previous 30 log returns, tick / future)."""
    k = ("z", id(t))
    if k not in _C:
        F = t.f[:, 3]; out = np.full(t.n, np.nan); tick = TICK[und(t)]
        r = np.full(t.n, np.nan)
        ok = np.isfinite(F[1:]) & np.isfinite(F[:-1]) & (F[1:] > 0) & (F[:-1] > 0)
        r[1:][ok] = np.log(F[1:][ok] / F[:-1][ok])
        for i in range(31, t.n):
            w = r[i - 30:i]
            if np.isfinite(w).all() and np.isfinite(r[i]):
                out[i] = r[i] / max(float(np.std(w)), tick / F[i])
        _C[k] = (out, r)
    return _C[k]


def lr(t):
    return fz(t)[1]


# ---------------------------------------------------------------- EN60: CUSUM, and its 5-minute-range control
XSPEC = {}     # (und, day, decision_i, setup) -> exit references (direction-free where a null may flip the side)


def cusum_signals(t, mode):
    k = ("cus", id(t), mode)
    if k in _C:
        return _C[k]
    dirs, sd, td = L3._blank(t); z, _ = fz(t); F, c = t.f[:, 3], t.close
    i0, iend = at(t, 750), at(t, 870); events = []
    if i0 < t.n and t.minute[i0] == 750:
        if mode == "CUSUM":
            Cp = Cm = 0.; zp = zm = i0; n = 0
            for i in range(i0 + 1, min(iend, t.n - 2) + 1):
                if not np.isfinite(z[i]):
                    continue
                Cp = max(0., Cp + z[i] - .25); Cm = max(0., Cm - z[i] - .25)
                if Cp == 0.:
                    zp = i
                if Cm == 0.:
                    zm = i
                for C, d, zi in ((Cp, 1, zp), (Cm, -1, zm)):
                    if C >= 4.5:
                        A = atr(t, i)
                        agree = np.isfinite([c[i], c[i - 2]]).all() and d * (c[i] - c[i - 2]) > 0
                        ev = dict(i=int(i), d=d, agree=bool(agree), origin=float(F[zi]))
                        if agree and np.isfinite(A) and options_at(t, i) and L4._avail(t, i, d):
                            dirs[i] = d; sd[i] = np.inf; n += 1
                            XSPEC[(und(t), t.day, int(i), mode)] = dict(kind="dist", F0=float(F[i]), atr0=A, dist=float(d * (F[i] - F[zi])) + .25 * A,
                                                                         copp=True)
                        events.append(ev); Cp = Cm = 0.; zp = zm = i
                        break
                if n >= 3:
                    break
        else:                                                   # CUSUM_ORB5: the five bars ending 12:30
            w = slice(i0 - 4, i0 + 1)
            if np.isfinite(t.f[w]).all():
                H, Lo = float(np.max(t.f[w, 1])), float(np.min(t.f[w, 2])); done = set()
                for i in range(i0 + 1, min(iend, t.n - 2) + 1):
                    if not np.isfinite(F[i]):
                        continue
                    for d, edge in ((1, H), (-1, Lo)):
                        if d in done or d * (F[i] - edge) <= 0:
                            continue
                        done.add(d); A = atr(t, i)
                        agree = np.isfinite([c[i], c[i - 2]]).all() and d * (c[i] - c[i - 2]) > 0
                        events.append(dict(i=int(i), d=d, agree=bool(agree), origin=edge))
                        if agree and np.isfinite(A) and options_at(t, i) and L4._avail(t, i, d):
                            dirs[i] = d; sd[i] = np.inf
                            XSPEC[(und(t), t.day, int(i), mode)] = dict(kind="dist", F0=float(F[i]), atr0=A, dist=float(d * (F[i] - edge)) + .25 * A,
                                                                         copp=False)
                    if len(done) == 2:
                        break
    _C[k] = (dirs, sd, td); _C[("ev", id(t), mode)] = events
    return _C[k]


# ---------------------------------------------------------------- EN64: price impact and its two controls
def impact_signals(t, mode):
    k = ("imp", id(t), mode)
    if k in _C:
        return _C[k]
    dirs, sd, td = L3._blank(t); r = lr(t); v = L5.fvol(t); F, c = t.f[:, 3], t.close
    imp = np.full(t.n, np.nan)
    for i in range(30, t.n):
        w = v[i - 30:i]
        if np.isfinite(r[i]) and np.isfinite(v[i]) and v[i] > 0 and np.isfinite(w).all() and (w > 0).all():
            imp[i] = abs(r[i]) / math.sqrt(max(.25, v[i] / float(np.median(w))))
    i0, iend = at(t, 751), at(t, 870); n = 0; cov = 0
    for i in range(max(i0, 61), min(iend, t.n - 2) + 1):
        if not np.isfinite(r[i - 2:i + 1]).all() or r[i] == 0 or not np.isfinite([c[i], c[i - 1]]).all():
            continue
        d = 1 if r[i] > 0 else -1; den = float(np.sum(np.abs(r[i - 2:i + 1])))
        eff = d * float(np.sum(r[i - 2:i + 1])) / den if den > 0 else 0.
        if mode == "IMPACT":
            wv = v[i - 60:i + 1]
            if not (np.isfinite(wv).all() and (wv > 0).all() and np.isfinite(imp[i - 30:i + 1]).all()):
                continue
            cov += 1; hit = imp[i] >= 3 * float(np.median(imp[i - 30:i]))
        elif mode == "IMPACT_RET":
            w = r[i - 30:i]
            if not np.isfinite(w).all():
                continue
            cov += 1; hit = abs(r[i]) >= 3 * float(np.median(np.abs(w)))
        else:                                                   # IMPACT_VOL
            w = v[i - 30:i]
            if not (np.isfinite(v[i]) and v[i] > 0 and np.isfinite(w).all() and (w > 0).all()):
                continue
            cov += 1; hit = v[i] >= 3 * float(np.median(w))
        if not hit or eff < .6 or d * (c[i] - c[i - 1]) <= 0:
            continue
        A = atr(t, i)
        if np.isfinite(A) and options_at(t, i) and L4._avail(t, i, d) and np.isfinite(t.f[i]).all():
            dirs[i] = d; sd[i] = np.inf; n += 1
            XSPEC[(und(t), t.day, int(i), mode)] = dict(kind="impact", F0=float(F[i]), atr0=A, hi=float(t.f[i, 1]), lo=float(t.f[i, 2]), e=int(i))
            if n >= 3:
                break
    _C[k] = (dirs, sd, td); _C[("cov", id(t), mode)] = cov
    return _C[k]


# ---------------------------------------------------------------- EN62: option-specific residual (cross-session)
GRID = tuple(range(750, 871, 5))
RULE62 = None                                           # set below (native contract inside Rs 2,500, 1.04 limit)
RES62 = {}                                             # (und, day) -> dict(mode -> (dirs, sd, td)), plus 'rows'


def bucket(m):
    return min(3, (m - 750) // 30)


def resid_rows(t):
    """Every grid time x side with a native contract inside Rs 2,500: residual and decay-only residual (decision-time
    data only: bars i and i-10)."""
    sp = L4.spec_of(t); out = []
    for m in GRID:
        i = at(t, m)
        if i >= t.n - 2 or t.minute[i] != m or i < 10:
            continue
        for d in (1, -1):
            if not options_at(t, i):
                continue
            pick = L4.choose4(sp, t, i, d, RULE62, 2500., 30000.)
            if not pick:
                continue
            j = pick[0]; x = resid_at(t, i, j)
            if x is not None:
                out.append(dict(i=i, d=d, j=j, b=bucket(m), res=x[0], dec=x[1]))
    return out


def resid_at(t, i, j, k=None):
    """(residual, decay-only residual) of contract j at bar k (default i) against its IV at i-10."""
    k = i if k is None else k; e = i - 10
    if e < 0 or not np.isfinite(t.q[[e, k], j, 3]).all() or t.q[e, j, 4] <= 0 or t.q[k, j, 4] <= 0:
        return None
    Fe, Fk = forward(t, e), forward(t, k)
    if not np.isfinite([Fe, Fk]).all():
        return None
    iv = ivol(t, e, j, Fe)
    if not np.isfinite(iv):
        return None
    K = float(t.strikes[j]); call = t.kinds[j] == 1; Tk = (930 - t.minute[k]) / YM; me = float(t.q[e, j, 3])
    obs = float(t.q[k, j, 3])
    return ((obs - price(Fk, K, Tk, iv, call)) / me, (obs - price(Fe, K, Tk, iv, call)) / me)


def prepare62(book):
    """Walk the book in date order; thresholds for each session from the preceding 20 covered expiries per bucket."""
    hist = {b: [] for b in range(4)}                    # bucket -> list of (day, [res], [dec]) per covered session
    for t in book:
        rows = resid_rows(t)
        th = {}
        for b in range(4):
            prev = hist[b][-20:]
            if len(prev) == 20:
                R_ = np.concatenate([np.array(p[1]) for p in prev]); D_ = np.concatenate([np.array(p[2]) for p in prev])
                th[b] = dict(p5=float(np.percentile(R_, 5)), med=float(np.median(R_)), p5d=float(np.percentile(D_, 5)),
                             medd=float(np.median(D_)))
        out = {}
        for mode in ("RESID", "RESID_DIR", "RESID_DECAY"):
            dirs, sd, td = L3._blank(t); n = 0
            for m in GRID:
                i = at(t, m)
                if i >= t.n - 2 or t.minute[i] != m or i < 3:
                    continue
                b = bucket(m)
                if b not in th or n >= 3:
                    continue
                F, c = t.f[:, 3], t.close; A = atr(t, i)
                if not (np.isfinite([F[i], F[i - 3], c[i], c[i - 3]]).all() and np.isfinite(A)):
                    continue
                mv = F[i] - F[i - 3]
                if abs(mv) < .5 * A:
                    continue
                d = 1 if mv > 0 else -1
                if d * (c[i] - c[i - 3]) <= 0 or not L4._avail(t, i, d):
                    continue
                row = next((r for r in rows if r["i"] == i and r["d"] == d), None)
                if row is None:
                    continue
                if mode == "RESID" and not row["res"] < th[b]["p5"]:
                    continue
                if mode == "RESID_DECAY" and not row["dec"] < th[b]["p5d"]:
                    continue
                if not np.isfinite(t.f[i - 2:i + 1]).all():
                    continue
                dirs[i] = d; sd[i] = np.inf; n += 1
                XSPEC[(und(t), t.day, int(i), mode)] = dict(kind="resid", F0=float(F[i]), atr0=A, med=th[b]["med" if mode != "RESID_DECAY" else "medd"],
                                                             decay=mode == "RESID_DECAY", target=mode != "RESID_DIR",
                                                             lo3=float(np.min(t.f[i - 2:i + 1, 2])), hi3=float(np.max(t.f[i - 2:i + 1, 1])))
            out[mode] = (dirs, sd, td)
        RES62[(und(t), t.day)] = dict(out, rows=len(rows), thresholds=th)
        for b in range(4):
            rb = [r for r in rows if r["b"] == b]
            if rb:
                hist[b].append((t.day, [r["res"] for r in rb], [r["dec"] for r in rb]))


SETUPS6 = {"CUSUM", "CUSUM_ORB5", "IMPACT", "IMPACT_RET", "IMPACT_VOL", "RESID", "RESID_DIR", "RESID_DECAY"}


def setup6(t, mode):
    if mode in ("CUSUM", "CUSUM_ORB5"):
        return cusum_signals(t, mode)
    if mode in ("IMPACT", "IMPACT_RET", "IMPACT_VOL"):
        return impact_signals(t, mode)
    got = RES62.get((und(t), t.day))
    assert got is not None, "prepare62(book) must run before RESID arms"
    return got[mode]


def signals6(t, rule):
    if rule.setup3 in SETUPS6:
        dirs, sd, td = setup6(t, rule.setup3)
        if L3.NULL is not None:
            dirs = L3.null_flip(t, dirs)
        return dirs, sd, td
    return L4.signals(t, rule)


# ---------------------------------------------------------------- exits for the round-6 setups
def xexit(t, i, pos):
    s = pos.get("xspec")
    if not s or pos.get("runner") or not np.isfinite(t.f[i, 3]):
        return None
    d = pos["direction"]; Fi = float(t.f[i, 3])
    if s["kind"] == "dist":
        if s["copp"]:
            z = fz(t)[0][i]
            if pos.get("copp_i") != i and np.isfinite(z):
                pos["copp"] = max(0., pos.get("copp", 0.) - d * z - .25); pos["copp_i"] = i
            if pos.get("copp", 0.) >= 2.25:
                return "CUSUM_REV"
        if d * (Fi - s["F0"]) < -s["dist"]:
            return "FSTOP"
        return None
    if s["kind"] == "impact":
        if (d > 0 and Fi < s["lo"] - .10 * s["atr0"]) or (d < 0 and Fi > s["hi"] + .10 * s["atr0"]):
            return "FSTOP"
        if i == s["e"] + 3:
            r = lr(t)[s["e"] + 1:s["e"] + 4]
            if np.isfinite(r).all():
                den = float(np.sum(np.abs(r)))
                if den == 0 or d * float(np.sum(r)) / den <= 0:
                    return "EFF_EXIT"
        return None
    if s["kind"] == "resid":
        if (d > 0 and Fi < s["lo3"]) or (d < 0 and Fi > s["hi3"]):
            return "FSTOP"
        if s["target"]:
            x = resid_at(t, pos["decision_i"], pos["j"], i)
            if x is not None and x[1 if s["decay"] else 0] >= s["med"]:
                return "RESID_TARGET"
    return None


def decide6(sp, t, i, pos, rule, bid, row):
    qty = pos["open"]
    if rule.ladder == "stop_only":
        pos["_intact"] = True
        if t.minute[i] >= rule.flat:
            return "FLAT_TIME", qty
        if bid is None or bid <= 0:
            return None, qty
        pos["peak"] = max(pos["peak"], bid)
        if bid <= pos["stop"]:
            return "STOP", qty
        x = xexit(t, i, pos)
        if x:
            return x, qty
        if i - pos["entry_i"] >= rule.hold:
            return "TIME", qty
        return None, qty
    if rule.core_bank and not pos.get("runner") and t.minute[i] < rule.flat and bid is not None and bid > 0:
        outlay = pos["entry"] * pos["lots"] * sp.lot + pos["fees"]
        if bid * pos["open"] * sp.lot - L4.fee(sp, bid, pos["open"] * sp.lot, False) >= 2 * outlay and pos["open"] == pos["lots"]:
            return "CORE_BANK", qty
    reason, qty = L4._decide(sp, t, i, pos, rule, bid, row)
    if reason is None:
        x = xexit(t, i, pos)
        if x:
            reason = x
    return reason, qty


# ---------------------------------------------------------------- EN63 contract choice
def friction(sp, cl):
    ask = L4.ask_of(cl)
    return (2 * E.half(cl) + (L4.fee(sp, ask, sp.lot, True) + L4.fee(sp, ask, sp.lot, False)) / sp.lot) / ask


def liq_pick(sp, t, i, d, rule, room, cash):
    c = float(t.close[i]); s = sp.step; atm = round(c / s) * s; first = math.floor(c / s) * s + s if d > 0 else math.ceil(c / s) * s - s
    best = None
    for k in dict.fromkeys((atm, atm - d * s, first)):
        js = [j for j in range(len(t.strikes)) if t.kinds[j] == d and float(t.strikes[j]) == float(k)]
        if not js or not np.isfinite(t.q[i, js[0]]).all() or int(t.q[i, js[0], 4] * .2) // sp.lot < 1:
            continue
        j = js[0]; cl = float(t.q[i, j, 3]); ask = L4.ask_of(cl)
        limit = E.down(min(ask * (1 + rule.chase), (min(room, cash) - 2 * sp.order) / (sp.lot * (1 + sp.buy_rate))))
        if limit < ask or L4.reserve(sp, limit, 1) > min(room, cash) + .01:
            continue
        cand = (round(friction(sp, cl), 9), abs(k - c), L4.reserve(sp, limit, 1), j, limit)
        if best is None or cand[:3] < best[:3]:
            best = cand
    if best is None:
        return None
    if rule.liq_pick == "cash":
        R_ = best[2]
        pick = L4.choose4(sp, t, i, d, replace(rule, max_lots=3), R_ + .005, cash)
        if not pick:
            return None
        CASHMATCH[(und(t), t.day, i)] = abs(L4.reserve(sp, pick[2], pick[1]) - R_) <= .10 * R_
        return pick
    return best[3], 1, best[4]


CASHMATCH = {}


# ---------------------------------------------------------------- the day loop (hooked copy of en_lab4.run_day4)
LOG_INTENTS = None             # a list to record every submitted entry intent (EN58 / EN70); None = off
KEEP6 = []                     # caches key on id(): keep built or truncated tapes alive (no id reuse)


def run_day6(t, rule, scenario="ordinary", cash=E.START_CASH, budget=E.BUDGET, details=False):
    sp = L4.spec_of(t); LOT = sp.lot; k = rule.size_k
    assert rule.setup3 not in ("PAIR", "PIN", "LASTHALF") and not rule.bank_r and not rule.regime_min and not rule.squeeze
    dirs, sdist, tdist = signals6(t, rule)
    spent = 0.0; positions = []; next_i = 0; pending_entry = None; pending_exit = None; pending_add = None; pos = None
    rejected = 0; missed = []; stopped = None; watch = None; intents = 0; start_cash = cash
    for i in range(int(np.searchsorted(t.minute, rule.start)), t.n):
        closed = None
        if pending_exit:
            qty, reason, decided = pending_exit
            filled, px = _exe(sp, t, i, pos["j"], "SELL", scenario, min(qty, pos["open"]))
            if filled:
                L4._sell(sp, pos, i, decided, reason, filled, px)
                if reason in ("TARGET_BASE", "PUT_RUNNER"):
                    pos["runner"] = True
                    pos["stop"] = max(round(pos["entry"] * rule.runner_floor, 2), round(pos["peak"] * rule.runner_keep, 2))
                if not pos["open"]:
                    cash = round(cash + pos["net"], 2); pos["exit_i"] = i; positions.append(pos); closed = pos
                    stopped = L3._stopped(t, pos, stopped); pos = None; pending_exit = None; next_i = i + 5
                else:
                    pending_exit = (pos["open"], reason, decided) if reason not in PARTIAL + ("PUT_RUNNER",) else None
            elif reason in PARTIAL + ("PUT_RUNNER",):
                pending_exit = None
            if pending_exit:
                continue
        if pending_add and pos:
            n, decided, lim, why = pending_add; pending_add = None
            if why == "ADD":
                pos["add_lots"] = 0
            filled, px = _exe(sp, t, i, pos["j"], "BUY", scenario, n)
            if filled and px is not None and px <= lim:
                left = pos["room"] - pos["reserve"]
                while filled and L4.reserve(sp, px, filled) > left + .01:
                    filled -= 1
                if filled:
                    spent += L4._buy_more(sp, pos, i, decided, filled, px, why,
                                          "max" if (rule.scout or why == "FALLBACK") and not rule.no_pstop else "none" if rule.no_pstop else "reset")
        if pending_entry:
            j, lots, limit, decision, sign, a_, room, origin, meta = pending_entry
            share = .2
            if rule.passive:
                r = t.q[i, j]; P = meta["passive"]; thr = P - (.05 if scenario == "ordinary" else .10)
                cap = int(r[4] * .2) // LOT if np.isfinite(r).all() else 0
                if cap > 0 and r[2] <= thr + 1e-9:
                    filled, px = min(lots, cap), P; pending_entry = None
                elif i - decision < 2:
                    continue
                else:
                    pending_entry = None; missed.append(dict(day=t.day, decision_i=decision, direction=sign, j=j)); continue
            elif rule.patient and meta.get("stage") != "fallback":
                r = t.q[i, j]; P = meta["passive"]; pending_entry = None
                if rule.patient == "cons":
                    thr, share = P - (.05 if scenario == "ordinary" else .10), .10
                else:
                    thr, share = P, .2
                thr -= PERT["ticks"] * .05
                cap = int(r[4] * share) // LOT if np.isfinite(r).all() else 0
                hit = cap > 0 and r[2] <= thr + 1e-9
                if hit and PERT["passive"] == "none":
                    hit = False
                elif hit and PERT["passive"] == "adversarial":
                    hit = _loses_later(t, j, decision, P)
                filled, px = (min(lots, cap), P) if hit else (0, None)
                rest = lots - filled
                ok_fb = rest > 0 and np.isfinite([t.f[i, 3], t.f[decision, 3], t.close[i]]).all() and sign * (t.f[i, 3] - t.f[decision, 3]) > 0
                lim2 = min(E.down(meta["ask0"] * 1.04), limit)
                if filled:
                    while filled and L4.reserve(sp, px, filled) > room + .01:
                        filled -= 1
                if not filled:
                    us = L4._us(t, rule, decision, sign, a_, meta)
                    if ok_fb and sign * (t.close[i] - us) > 0 and t.minute[i] < rule.end + 1 and i < t.n - 1:
                        meta = dict(meta, stage="fallback"); pending_entry = (j, lots, lim2, decision, sign, a_, room, origin, meta)
                    else:
                        missed.append(dict(day=t.day, decision_i=decision, direction=sign, j=j))
                    continue
                if rest and ok_fb:
                    meta = dict(meta, fb=(rest, lim2))
            else:
                pending_entry = None
                filled, px = _exe(sp, t, i, j, "BUY", scenario, lots)
            if filled < max(1, math.ceil(lots * .25)) or px is None or px > limit:
                if not (rule.patient and filled and px is not None and px <= limit):
                    rejected += 1; continue
            risk = L4.reserve(sp, px, filled); assert risk <= room + .01
            spent += risk
            pos = L4._open(sp, t, i, rule, j, filled, px, decision, sign, a_, room, origin, meta); pos["rule_stop"] = rule.stop
            if meta.get("fb"):
                pos["fallback"] = (meta["fb"][0], decision, meta["fb"][1])
            if meta.get("xspec"):
                pos["xspec"] = dict(meta["xspec"])
        if pos:
            row = t.q[i, pos["j"]]
            bid = E.down(float(row[3]) - E.half(float(row[3]))) if np.isfinite(row[3]) and np.isfinite(row[4]) and row[4] * .2 >= LOT else None
            if rule.fast_exit and not pos.get("runner") and t.minute[i] < rule.flat:
                fx = L4._fast(sp, t, i, pos, rule, scenario)
                if fx:
                    filled, px, reason = fx; L4._sell(sp, pos, i, i, reason, filled, px)
                    if not pos["open"]:
                        cash = round(cash + pos["net"], 2); pos["exit_i"] = i; positions.append(pos); closed = pos
                        stopped = L3._stopped(t, pos, stopped); pos = None; next_i = i + 5
                    elif i < t.n - 1:
                        pending_exit = (pos["open"], reason, i)
                    if pos is not None:
                        continue
            if pos is not None:
                reason, qty = decide6(sp, t, i, pos, rule, bid, row)
                if reason is None and pos.get("fallback") and i < t.n - 1:
                    n, decided, lim2 = pos["fallback"]; pos["fallback"] = None
                    if pos["direction"] * (t.close[i] - pos["underlying_stop"]) > 0:
                        pending_add = (n, decided, lim2, "FALLBACK")
                elif reason is None and rule.scout and pos["add_lots"] and not pos.get("runner") and 2 <= i - pos["entry_i"] <= 6 \
                        and i - pos["entry_i"] < rule.hold and bid is not None and i >= 1 and L4._progress(t, i, pos):
                    pending_add = (pos["add_lots"], i, E.down(L4.ask_of(row[3]) * (1 + rule.chase)), "ADD")
                elif reason is None and rule.scale_in and pos["add_lots"] and not pos.get("runner") and i - pos["entry_i"] <= 3 \
                        and pos.get("_intact") and bid is not None and bid >= pos["first"] * 1.2 and np.isfinite(row[3]):
                    pending_add = (pos["add_lots"], i, E.down(E.up(float(row[3]) + E.half(float(row[3]))) * (1 + rule.chase)), "ADD")
                if reason:
                    pos["fallback"] = None
                if reason and i < t.n - 1:
                    pending_exit = (qty, reason, i)
                continue
        if closed is not None and rule.reverse:
            watch = L4._arm_watch(t, rule, closed, i, len(positions))
        if pending_exit or pending_entry or i >= t.n - 1 or len(positions) >= rule.slots:
            continue
        if rule.max_intents and intents >= rule.max_intents:
            continue
        sign, meta, normal = 0, {}, False
        if watch:
            sign, meta, watch = L4._watch(t, rule, watch, i)
        if not sign:
            normal = True
            if i < next_i:
                continue
            sign = int(dirs[i])
            if not sign:
                continue
            if sdist is not None:
                meta.update(sd=float(sdist[i]), td=float(tdist[i]))
            if stopped and rule.no_retry_after_stop:
                continue
            if stopped and rule.retry_gate and sign == stopped["d"]:
                if not (np.isfinite(t.x[i - 2:i]).all() and np.isfinite(t.f[i, 3])):
                    continue
                pull = float(np.min(t.x[i - 2:i, 2]) if sign > 0 else np.max(t.x[i - 2:i, 1]))
                c0, f0 = stopped["c0"], stopped["f0"]
                if not (sign * (t.close[i] - c0) > 0 and sign * (t.f[i, 3] - f0) > 0 and sign * (pull - c0) > 0):
                    continue
                meta.update(slevel=pull, max_lots=stopped["lots"])
        mult = rule.put_mult if sign < 0 else rule.call_mult
        room = min(E.BUDGET / rule.slots * mult * k, budget - spent, cash)
        if rule.parent_cap:
            room = min(room, rule.parent_cap)
        if room <= 0:
            continue
        cap = int(round(rule.max_lots * mult * k))
        if rule.atm_itm:
            pick = L4.choose_atm(sp, t, i, sign, room, rule.chase)
        elif rule.liq_pick:
            pick = liq_pick(sp, t, i, sign, rule, room, cash)
        else:
            pick = L4.choose4(sp, t, i, sign, replace(rule, max_lots=cap) if cap != rule.max_lots else rule, room, cash)
        if pick:
            j, lots, limit = pick
            if meta.get("max_lots"):
                lots = min(lots, meta["max_lots"])
            if (rule.scale_in or rule.scout) and lots >= 2:
                first = math.ceil(lots / 2); meta.update(add=lots - first, planned=lots); lots = first
            if rule.passive or rule.patient:
                qc = float(t.q[i, j, 3]); meta["passive"] = E.down(qc - E.half(qc)); meta["ask0"] = L4.ask_of(qc)
                if meta["passive"] <= 0:
                    continue
            origin = meta.pop("origin", None) or ("E032" if not rule.setup3 else rule.setup3)
            if rule.setup3 in SETUPS6:
                meta["xspec"] = XSPEC.get((und(t), t.day, int(i), rule.setup3))
            pending_entry = (j, lots, limit, i, sign, t.features[rule.look][i, 4], room, origin, meta); intents += 1
            if LOG_INTENTS is not None:
                LOG_INTENTS.append(dict(day=t.day, i=int(i), d=int(sign), j=int(j), lots=int(lots), limit=float(limit), room=float(room),
                                        ask0=float(L4.ask_of(t.q[i, j, 3])), passive=meta.get("passive"), planned=int(meta.get("planned", lots))))
            if normal:
                watch = None
    unresolved = 0
    if pos:
        unresolved = 1
        pos["net"] = round(pos["net"] - pos["entry"] * pos["open"] * LOT, 2); pos["unresolved"] = True; positions.append(pos)
    child = None
    if rule.core_bank and rule.core_child and positions and not unresolved:
        core = positions[0]
        first = next((e["reason"] for e in core["events"] if e["side"] == "SELL"), "")
        if first == "CORE_BANK" and core["net"] > 0 and not core.get("unresolved"):
            child = run_child(sp, t, core, rule, scenario, budget - spent, cash)
            if child.get("lots"):
                spent += child["reserve"]; positions.append(child)
                if child.get("unresolved"):
                    unresolved = 1
    net = round(sum(p["net"] for p in positions), 2)
    assert spent <= budget + .02 and net >= -spent - .03, (t.day, spent, budget, net)
    mw = marked_worst(sp, t, positions)
    out = dict(day=t.day, net=net, trades=len([p for p in positions if p.get("origin") != "CHILD"]), spent=round(spent, 2),
               fees=round(sum(p["fees"] for p in positions), 2), unresolved=unresolved, rejected=rejected,
               positions=positions if details else [], marked_worst=mw, calm=False, missed=missed if details else [], intents=intents)
    if rule.core_bank:
        out["child"] = None if child is None else dict(reason=child.get("why"), net=child.get("net", 0.), lots=child.get("lots", 0))
    return out


def run_child(sp, t, core, rule, scenario, budget_left, cash):
    """EN65: one child of the core's direction, funded by <= half of the realised core profit G (<= Rs 500)."""
    d = core["direction"]; e = core["exit_i"]; G = core["net"]; LOT = sp.lot
    res_c = min(.5 * G, 500., budget_left, cash)
    c, F = t.close, t.f[:, 3]
    if e >= t.n - 2 or t.minute[e] >= rule.flat or e < 2:
        return dict(why="late")
    if not (np.isfinite([c[e], c[e - 2], F[e], F[e - 2]]).all() and d * (c[e] - c[e - 2]) > 0 and d * (F[e] - F[e - 2]) > 0):
        return dict(why="direction")
    ci = float(c[e]); pick = None
    for j in sorted([j for j in range(len(t.strikes)) if t.kinds[j] == d and d * (t.strikes[j] - ci) > 0], key=lambda j: d * t.strikes[j]):
        r = t.q[e, j]
        if not np.isfinite(r).all() or int(r[4] * .2) // LOT < 1:
            continue
        ask = L4.ask_of(r[3]); limit = E.down(ask * 1.04)
        if limit >= ask and L4.reserve(sp, limit, 1) <= res_c + .01:
            pick = (j, limit); break
    if pick is None:
        return dict(why="unaffordable", res_c=round(res_c, 2))
    j, limit = pick
    filled, px = _exe(sp, t, e + 1, j, "BUY", scenario, 1)
    if not filled or px is None or px > limit:
        return dict(why="nofill")
    f0 = L4.fee(sp, px, LOT, True)
    ch = dict(day=t.day, j=j, symbol=t.symbols[j], direction=d, entry_i=e + 1, decision_i=e, entry=px, lots=1, open=1,
              reserve=round(L4.reserve(sp, px, 1), 2), peak=px, net=-f0, fees=f0, origin="CHILD", why="child", runner=False,
              first=px, events=[dict(i=e + 1, decision_i=e, side="BUY", lots=1, price=px, fees=f0)])
    pend = None
    for i in range(e + 1, t.n):
        if pend:
            filled, sp_ = _exe(sp, t, i, j, "SELL", scenario, 1)
            if filled:
                L4._sell(sp, ch, i, pend[1], pend[0], 1, sp_); ch["exit_i"] = i; pend = None; break
            continue
        if i >= t.n - 1:
            break
        row = t.q[i, j]
        if t.minute[i] >= rule.flat:
            pend = ("FLAT_TIME", i); continue
        if not (np.isfinite(row[3]) and np.isfinite(row[4]) and row[4] * .2 >= LOT):
            continue
        bid = L4.bid_of(row[3]); ch["peak"] = max(ch["peak"], bid)
        if bid >= 2 * ch["entry"]:
            ch["runner"] = True
        stop = max(ch["entry"], .5 * ch["peak"]) if ch["runner"] else .65 * ch["entry"]
        if bid <= stop:
            pend = ("CHILD_TRAIL" if ch["runner"] else "CHILD_STOP", i)
        elif bid >= 10 * ch["entry"]:
            pend = ("HERO_TARGET", i)
        elif np.isfinite(c[i]) and d * (c[i] - core["underlying_stop"]) < 0:
            pend = ("STRUCTURE", i)
        elif i - ch["entry_i"] >= 15:
            pend = ("TIME", i)
    if ch["open"]:
        ch["net"] = round(ch["net"] - ch["entry"] * LOT, 2); ch["unresolved"] = True
    ch["res_c"] = round(res_c, 2)
    assert ch["net"] >= -ch["reserve"] - .01 and ch["reserve"] <= res_c + .01
    assert G + ch["net"] >= G - res_c - .01 >= G / 2 - .01, (t.day, G, ch["net"], res_c)
    return ch


def marked_worst(sp, t, positions):
    """Worst intratrade equity of the day: cash flows so far + open lots at each bar's low bid less sell charges."""
    if not positions:
        return 0.
    lo = min(p["entry_i"] for p in positions); hi = max(p.get("exit_i", t.n - 1) for p in positions)
    worst = 0.
    for b in range(lo, hi + 1):
        eq = 0.
        for p in positions:
            flows = 0.; open_ = 0
            for ev in p["events"]:
                if ev["i"] > b:
                    continue
                amt = ev["price"] * ev["lots"] * sp.lot
                if ev["side"] == "BUY":
                    flows -= amt + ev["fees"]; open_ += ev["lots"]
                else:
                    flows += amt - ev["fees"]; open_ -= ev["lots"]
            if open_ > 0:
                lw = t.q[b, p["j"], 2]
                bidl = E.down(float(lw) - E.half(float(lw))) if np.isfinite(lw) else 0.
                flows += max(0., bidl * open_ * sp.lot - L4.fee(sp, bidl, open_ * sp.lot, False)) if bidl > 0 else 0.
            eq += flows
        worst = min(worst, eq)
    return round(worst, 2)


# ---------------------------------------------------------------- arms (PLAN6.md)
RULE62 = replace(E032, chase=.04, max_lots=3)
ARMS = {
    "E032_30k": E032, "EN55": EN55, "E032_sym": SYM,
    "E032_env": R6(E032, **ENV),
    # EN60
    "EN60": R6(E032, setup3="CUSUM", **NEW6),
    "EN60_orb5_ctl": R6(E032, setup3="CUSUM_ORB5", **NEW6),
    "EN60_1250_diag": R6(E032, setup3="CUSUM", day_budget=1250., **NEW6),
    # EN62
    "EN62": R6(E032, setup3="RESID", ladder="stop_only", **NEW6),
    "EN62_dir_ctl": R6(E032, setup3="RESID_DIR", ladder="stop_only", **NEW6),
    "EN62_decay_ctl": R6(E032, setup3="RESID_DECAY", ladder="stop_only", **NEW6),
    "EN62_1250_diag": R6(E032, setup3="RESID", ladder="stop_only", day_budget=1250., **NEW6),
    # EN64
    "EN64": R6(E032, setup3="IMPACT", **NEW6),
    "EN64_ret_ctl": R6(E032, setup3="IMPACT_RET", **NEW6),
    "EN64_vol_ctl": R6(E032, setup3="IMPACT_VOL", **NEW6),
    "EN64_1250_diag": R6(E032, setup3="IMPACT", day_budget=1250., **NEW6),
    # EN63 (2 x 2, one lot, one Rs 2,500 parent, 1.04 limit)
    "EN63": R6(E032, liq_pick="liq", max_lots=1, chase=.04, hold=15, **ENV),
    "EN63_native8_ctl": R6(E032, max_lots=1, chase=.04, **ENV),
    "EN63_native15": R6(E032, max_lots=1, chase=.04, hold=15, **ENV),
    "EN63_liq8": R6(E032, liq_pick="liq", max_lots=1, chase=.04, **ENV),
    "EN63_cash_diag": R6(E032, liq_pick="cash", chase=.04, hold=15, **ENV),
    # EN65
    "EN65": R6(E032, core_bank=True, core_child=True, target=1e9, parent_cap=2000., **ENV),
    "EN65_bank_ctl": R6(E032, core_bank=True, target=1e9, parent_cap=2000., **ENV),
    "EN65_en12_diag": R6(E032, cover=True, runner_struct=True, **ENV),
    # EN67
    "EN67": R6(EN55, start=750, efficiency=.6),
}
for eff in (.5, .6, .7, .8):
    for st in (750, 780):
        ARMS[f"EN67_e{int(eff * 10)}_s{st}_diag"] = R6(EN55, start=st, efficiency=eff)
for p in ("", "cons"):
    for sc in (False, True):
        for rs in (False, True):
            ARMS[f"EN57_p{int(bool(p))}s{int(sc)}r{int(rs)}"] = R6(E032, patient=p, scout=sc, runner_stall=rs)


# ---------------------------------------------------------------- EN59: pair engine with per-leg ledger
@dataclass(frozen=True)
class Pair:
    mode: str = "package"          # 'package' (EN59), 'legout' (EN52), 'bracket' (EN51 / close-at-b), 'hold'
    at: int = 780
    target: float = .25
    stop: float = .25
    legout: float = 1.5
    pkg_gate: float = .10          # EN59 condition (b): pair after-fee P&L >= 10% of the outlay before a leg-out
    reserve: float = 2500.
    flat: int = 914
    runner_keep: float = .5
    hero: float = 9.

    @property
    def key(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


def pair_day(t, s, scenario="ordinary", cash=30000., budget=None, details=False):
    """One lot each of the 13:00 ATM call and put. 'legout' and 'bracket' replicate en_lab5.straddle_day exactly
    (check() proves it); 'package' is EN59. Every leg's buy and sale is its own ledger event."""
    sp = L4.spec_of(t); LOT = sp.lot; budget = s.reserve if budget is None else budget
    i0 = at(t, s.at)
    empty = dict(day=t.day, net=0., trades=0, spent=0., fees=0., unresolved=0, rejected=0, positions=[], marked_worst=0., calm=False,
                 missed=[], refusal=None, intents=0)
    if i0 >= t.n - 2 or t.minute[i0] != s.at or not np.isfinite(t.close[i0]):
        return dict(empty, refusal="no_bar")
    K = round(float(t.close[i0]) / sp.step) * sp.step
    js = {int(t.kinds[j]): j for j in range(len(t.strikes)) if float(t.strikes[j]) == K}
    if len(js) < 2 or not all(np.isfinite(t.q[i0, j]).all() for j in js.values()):
        return dict(empty, refusal="no_atm_pair")
    room = min(s.reserve, budget, cash); legs = []
    for d in (1, -1):
        j = js[d]; ask = L4.ask_of(t.q[i0, j, 3]); legs.append(dict(j=j, d=d, limit=E.down(ask * 1.04)))
    spent = sum(L4.reserve(sp, g["limit"], 1) for g in legs)
    if spent > room + .01:
        return dict(empty, refusal="reserve", intents=0)
    got = []
    for g in legs:
        f, p = _exe(sp, t, i0 + 1, g["j"], "BUY", scenario, 1)
        if f and p is not None and p <= g["limit"]:
            fee0 = L4.fee(sp, p, LOT, True)
            got.append(dict(g, entry=p, open=1, net=-fee0, fees=fee0, peak=p, sells=[],
                            events=[dict(i=i0 + 1, decision_i=i0, side="BUY", lots=1, price=p, fees=fee0)], entry_i=i0 + 1))
    if not got:
        return dict(empty, rejected=1, refusal="unfilled", spent=round(spent, 2), intents=1)
    cost = sum(g["entry"] * LOT + g["fees"] for g in got)
    pend = {}; runner = None if len(got) == 2 else got[0]; reason = None if len(got) == 2 else "ONE_LEG"
    weak_cash = None; pk_max = 0.
    if reason:
        pend[id(got[0])] = reason
    for i in range(i0 + 1, t.n):
        for g in got:
            if g["open"] and id(g) in pend:
                f, p = _exe(sp, t, i, g["j"], "SELL", scenario, 1)
                if f:
                    c = L4.fee(sp, p, LOT, False); g["net"] += (p - g["entry"]) * LOT - c; g["fees"] += c; g["open"] = 0
                    why = pend.pop(id(g)); g["sells"].append(dict(i=i, reason=why, price=p))
                    g["events"].append(dict(i=i, decision_i=i - 1, side="SELL", lots=1, price=p, fees=c, reason=why)); g["exit_i"] = i
                    if why == "LEG_OUT":
                        weak_cash = p * LOT - c
        if not any(g["open"] for g in got) or i >= t.n - 1:
            break
        live = [g for g in got if g["open"] and id(g) not in pend]
        if not live:
            continue
        bids = {}
        for g in live:
            r = t.q[i, g["j"]]
            bids[id(g)] = L4.bid_of(r[3]) if np.isfinite(r).all() and r[4] * .2 >= LOT else None
        if t.minute[i] >= s.flat:
            for g in live:
                pend[id(g)] = "FLAT_TIME"
            continue
        if runner is not None:
            b = bids.get(id(runner))
            if s.mode == "package" and reason is None:
                if b and weak_cash is not None:
                    P = weak_cash + (b * LOT - L4.fee(sp, b, LOT, False)) - cost; pk_max = max(pk_max, P)
                    if P < .5 * pk_max or (pk_max == 0. and P < 0):
                        pend[id(runner)] = "PACKAGE_FLOOR"
                    elif b >= runner["entry"] * (1 + s.hero):
                        pend[id(runner)] = "HERO_TARGET"
                continue
            if b:
                runner["peak"] = max(runner["peak"], b)
                stop = max(runner["entry"], runner["peak"] * s.runner_keep)
                if b <= stop:
                    pend[id(runner)] = "RUNNER_TRAIL"
                elif b >= runner["entry"] * (1 + s.hero):
                    pend[id(runner)] = "HERO_TARGET"
            continue
        if any(bids[id(g)] is None for g in live):
            continue
        V = sum(bids[id(g)] * LOT - L4.fee(sp, bids[id(g)], LOT, False) for g in live)
        if s.mode == "hold":
            continue
        if V <= (1 - s.stop) * cost:
            for g in live:
                pend[id(g)] = "STOP"
        elif s.mode == "bracket" and V >= (1 + s.target) * cost:
            for g in live:
                pend[id(g)] = "TARGET"
        elif s.mode in ("legout", "package"):
            for g in live:
                if bids[id(g)] >= s.legout * g["entry"] and (s.mode == "legout" or V - cost >= s.pkg_gate * cost):
                    other = [h for h in live if h is not g][0]; pend[id(other)] = "LEG_OUT"; runner = g; g["peak"] = bids[id(g)]
                    break
    unresolved = 0
    for g in got:
        if g["open"]:
            unresolved = 1; g["net"] -= g["entry"] * LOT
    net = round(sum(g["net"] for g in got), 2)
    assert net >= -spent - .05, (t.day, net, spent)
    legs_pos = [dict(j=g["j"], entry_i=g["entry_i"], exit_i=g.get("exit_i", t.n - 1), events=g["events"]) for g in got]
    mw = marked_worst(sp, t, legs_pos)
    pos = dict(day=t.day, decision_i=i0, entry_i=i0 + 1, direction=0, lots=len(got), entry=round(sum(g["entry"] for g in got), 2),
               first=round(sum(g["entry"] for g in got), 2), net=net, fees=round(sum(g["fees"] for g in got), 2), origin="PAIR",
               symbol=f"{und(t)}-{K:g}", legs=[dict(kind=g["d"], j=g["j"], entry=g["entry"], net=round(g["net"], 2), events=g["events"]) for g in got],
               events=[e for g in got for e in g["events"]], unresolved=bool(unresolved),
               exit_i=max([x["i"] for g in got for x in g["sells"]], default=t.n - 1))
    return dict(day=t.day, net=net, trades=1, spent=round(spent, 2), fees=pos["fees"], unresolved=unresolved, rejected=0,
                positions=[pos] if details else [], marked_worst=mw, calm=False, missed=[], refusal=None, intents=1)


PAIRS = {
    "EN59": Pair("package"),
    "EN59_en52_ctl": Pair("legout"),
    "EN59_en52_5000": Pair("legout", reserve=5000.),
    "EN59_closeb_diag": Pair("bracket", target=.10),
    "EN59_en51_2500": Pair("bracket"),
}
ARMS.update(PAIRS)


# ---------------------------------------------------------------- books, fixed-cap and wallet
DAYFN = {}                                             # type -> day function (en_ml6 registers EN61's executor)


def budget_of(arm):
    if isinstance(arm, (Pair, L5.Straddle)):
        return arm.reserve
    if isinstance(arm, L5.Rule):
        return (arm.day_budget or E.BUDGET * R.day_scale(arm)) * arm.size_k
    return arm.reserve


def day6(t, arm, scenario, cash, budget, details):
    if isinstance(arm, Pair):
        return pair_day(t, arm, scenario, cash, budget, details)
    if isinstance(arm, L5.Straddle):
        return L5.straddle_day(t, arm, scenario, cash, budget, details)
    if type(arm) in DAYFN:
        return DAYFN[type(arm)](t, arm, scenario, cash, budget, details)
    return run_day6(t, arm, scenario, cash, budget, details)


def run_fixed6(book, arm, scenario="ordinary", details=False, cash=30000.):
    days = [day6(t, arm, scenario, cash, budget_of(arm), details) for t in book]
    return dict(days=days, summary=E.summary(days))


def run_wallet6(book, arm, scenario="ordinary", start=30000., retain=.5, details=False, pre=None):
    """en_lab5.run_wallet (check() proves equality) plus the liquidation drawdown: the trading high-water minus the
    worst intratrade marked equity. `pre` optionally supplies day results by (und, day, scale) (EN68's replay)."""
    P = W = peakP = 0.; days = []; full = budget_of(arm); liq = 0.
    for t in book:
        cash = start + P - W; dd = peakP - P
        scale = 0. if dd >= 4000 else .25 if dd >= 3000 else .5 if dd >= 1500 else 1.
        if pre is not None:
            row = dict(pre[(und(t), t.day, scale)])
        else:
            row = day6(t, arm, scenario, cash, min(full * scale, cash), details)
        liq = max(liq, peakP - (P + min(0., row.get("marked_worst", 0.))))
        P = round(P + row["net"], 2); peakP = max(peakP, P)
        sweep = round(max(0., retain * max(P, 0.) - W), 2) if retain else 0.
        W = round(W + sweep, 2)
        assert abs((start + P - W) + W - (start + P)) < 1e-6 and start + P - W >= -.01
        row.update(scale=scale, P=P, W=W, cash_after=round(start + P - W, 2), sweep=sweep); days.append(row)
    s = E.summary(days)
    hw = 0.; cdd = 0.
    for d in days:
        hw = max(hw, d["P"]); cdd = max(cdd, hw - d["P"])
    return dict(days=days, summary=s, P=P, swept=W, wallet=round(start + P - W, 2), halted=sum(d["scale"] == 0. for d in days),
                first_halt=next((d["day"] for d in days if d["scale"] == 0.), None), liq_dd=round(liq, 2), close_dd=round(cdd, 2))


def books():
    B = L5.books()
    for t in B["SENSEX"]:
        assert und(t) == "SENSEX"
    return B


def combined(B):
    """EN66: NIFTY and SENSEX sessions in date order on their common period (NIFTY first on a shared date)."""
    lo, hi = B["SENSEX"][0].day, B["SENSEX"][-1].day
    xs = [(t.day, 0, t) for t in B["NIFTY"] if lo <= t.day <= hi] + [(t.day, 1, t) for t in B["SENSEX"]]
    return [t for _, _, t in sorted(xs, key=lambda x: (x[0], x[1]))]


# ---------------------------------------------------------------- EN56: the executable opportunity library
HOR = (3, 8, 15, 30)
RES = (1250., 2500.)
OFFS = (-1, 0, 1, 2)
LIBF = ("i", "m", "d", "off", "R", "lots", "status", "h", "censored", "net", "gross", "fees", "slip_in", "slip_out", "net_nospread",
        "mae", "mfe", "t_pos", "dF_atr", "delta_rs", "buy", "unresolved", "j", "e")
ST = {"FILLED": 0, "NO_FILL": 1, "UNAFFORDABLE": 2, "MISSING": 3}


def delta_of(t, i, j):
    Fw = forward(t, i); iv = ivol(t, i, j, Fw) if np.isfinite(Fw) else math.nan
    if not np.isfinite(iv):
        return math.nan
    K = float(t.strikes[j]); call = t.kinds[j] == 1; T = (930 - t.minute[i]) / YM; h = Fw * 1e-4
    return (price(Fw + h, K, T, iv, call) - price(Fw - h, K, T, iv, call)) / (2 * h)


def _blank_rows(i, m, d, off, st, lots=0, j=-1):
    return [(i, m, d, off, R_, lots, st, h, 0, 0., 0., 0., 0., 0., 0., 0., 0., -1, math.nan, math.nan, 0., 0, j, -1)
            for R_ in RES for h in HOR]


def library(t, scenario="ordinary", decisions=None):
    """Rows (tuples in LIBF order). decisions: None = the 5-minute grid x both sides; else [(i, d), ...]."""
    sp = L4.spec_of(t); LOT = sp.lot; out = []; ef = at(t, 915)
    cols = {(float(k), int(kd)): j for j, (k, kd) in enumerate(zip(t.strikes, t.kinds))}
    if decisions is None:
        decisions = [(at(t, m), d) for m in GRID for d in (1, -1) if at(t, m) < t.n and t.minute[at(t, m)] == m]
    for i, d in decisions:
        if i >= t.n - 2 or not np.isfinite(t.close[i]):
            continue
        m = int(t.minute[i]); c = float(t.close[i]); atm = round(c / sp.step) * sp.step; A = atr(t, i)
        for off in OFFS:
            K = atm + d * off * sp.step; j = cols.get((float(K), d))
            if j is None or not np.isfinite(t.q[i, j]).all():
                out += _blank_rows(i, m, d, off, ST["MISSING"]); continue
            ask = L4.ask_of(t.q[i, j, 3]); limit = E.down(ask * 1.04); dl = None
            for R_ in RES:
                lots = next((l for l in (3, 2, 1) if L4.reserve(sp, limit, l) <= R_ + .01), 0)
                if not lots:
                    out += [r for r in _blank_rows(i, m, d, off, ST["UNAFFORDABLE"], 0, j) if r[4] == R_]; continue
                f, p = _exe(sp, t, i + 1, j, "BUY", scenario, lots)
                if not f or p is None or p > limit:
                    out += [r for r in _blank_rows(i, m, d, off, ST["NO_FILL"], lots, j) if r[4] == R_]; continue
                u = f * LOT; buy = p * u; bf = L4.fee(sp, p, u, True); o1 = float(t.q[i + 1, j, 0])
                if dl is None:
                    dl = delta_of(t, i, j)
                for h in HOR:
                    e0 = i + 1 + h; cen = int(e0 > ef); e = min(e0, ef); sale = None
                    for k in range(e, t.n):
                        fs, p2 = _exe(sp, t, k, j, "SELL", scenario, f)
                        if fs:
                            sale = (k, p2); break
                    end = sale[0] if sale else t.n
                    mae = mfe = 0.; tpos = -1
                    for b in range(i + 1, end):
                        r = t.q[b, j]
                        if not np.isfinite(r).all():
                            continue
                        bl, bh, bc = L4.bid_of(r[2]), L4.bid_of(r[1]), L4.bid_of(r[3])
                        vl = bl * u - L4.fee(sp, bl, u, False) - buy - bf; vh = bh * u - L4.fee(sp, bh, u, False) - buy - bf
                        mae, mfe = min(mae, vl), max(mfe, vh)
                        if tpos < 0 and bc * u - L4.fee(sp, bc, u, False) - buy - bf > 0:
                            tpos = b - (i + 1)
                    Fd = t.f[i, 3]; Fe = t.f[end - 1, 3]
                    dF = d * (Fe - Fd) if np.isfinite([Fd, Fe]).all() else math.nan
                    dfa = dF / A if np.isfinite(A) and A > 0 and np.isfinite(dF) else math.nan
                    drs = abs(dl) * dF * u if np.isfinite(dl) and np.isfinite(dF) else math.nan
                    if sale:
                        k, p2 = sale; sf = L4.fee(sp, p2, u, False); gross = (p2 - p) * u; net = gross - bf - sf
                        ok_ = float(t.q[k, j, 0]) if np.isfinite(t.q[k, j, 0]) else p2
                        out.append((i, m, d, off, R_, f, ST["FILLED"], h, cen, round(net, 2), round(gross, 2), round(bf + sf, 2),
                                    round((p - o1) * u, 2), round((ok_ - p2) * u, 2), round((ok_ - o1) * u - bf - sf, 2), round(mae, 2),
                                    round(mfe, 2), tpos, dfa, drs, round(buy, 2), 0, j, k))
                    else:
                        out.append((i, m, d, off, R_, f, ST["FILLED"], h, cen, round(-buy - bf, 2), round(-buy, 2), round(bf, 2),
                                    round((p - o1) * u, 2), 0., round(-buy - bf, 2), round(mae, 2), round(mfe, 2), tpos, dfa, drs,
                                    round(buy, 2), 1, j, -1))
    return out


# ---------------------------------------------------------------- EN69: sequential full-revaluation decomposition
def decompose(t, j, b0, b1):
    """Per unit, from the close of bar b0 to the close of bar b1 for contract j: underlying, time, volatility."""
    C0, C1 = float(t.q[b0, j, 3]), float(t.q[b1, j, 3])
    F0, F1 = forward(t, b0), forward(t, b1)
    if not np.isfinite([C0, C1, F0, F1]).all():
        return None
    s0, s1 = ivol(t, b0, j, F0), ivol(t, b1, j, F1); K = float(t.strikes[j]); call = t.kinds[j] == 1
    T0, T1 = (930 - t.minute[b0]) / YM, (930 - t.minute[b1]) / YM
    if not np.isfinite([s0, s1]).all():
        return dict(ok=False, mark=C1 - C0, dF=F1 - F0)
    v00 = price(F0, K, T0, s0, call); v10 = price(F1, K, T0, s0, call); v11 = price(F1, K, T1, s0, call); v111 = price(F1, K, T1, s1, call)
    return dict(ok=True, underlying=v10 - v00, time=v11 - v10, vol=v111 - v11, model_err=(C1 - C0) - (v111 - v00), mark=C1 - C0,
                d_iv=s1 - s0, dF=F1 - F0)


# ---------------------------------------------------------------- checks (counts only, no rupees printed)
def _truncated(t, i):
    u = D4._D().Tape(t.day, t.x.copy(), t.f.copy(), t.q.copy(), t.strikes, t.kinds, t.symbols, t.now, t.minute, t.invalid)
    u.x[i + 1:] = np.nan; u.f[i + 1:] = np.nan; u.q[i + 1:] = np.nan
    if hasattr(t, "und"):
        u.und = t.und
    KEEP6.append(u)
    return u


def _fillbar_changed(t, i):
    """The audit's counterexample: only the next bar's option prices change."""
    u = D4._D().Tape(t.day, t.x.copy(), t.f.copy(), t.q.copy(), t.strikes, t.kinds, t.symbols, t.now, t.minute, t.invalid)
    u.q[i + 1:, :, :4] *= 1.2
    if hasattr(t, "und"):
        u.und = t.und
    KEEP6.append(u)
    return u


def check_parity(B):
    """run_day6 == run_day4 day by day for every round-5 run_day4 arm, both books, three fill levels (hooks off);
    run_wallet6 == en_lab5.run_wallet; pair_day == en_lab5.straddle_day for EN51 / EN52 at Rs 5,000 and Rs 2,500."""
    L5.prepare(B)
    n = 0
    for name, arm in L5.ARMS.items():
        if isinstance(arm, L5.Straddle):
            continue
        r6 = R6(arm)
        for bk, book in B.items():
            for sc in ("ordinary", "adverse", "catastrophe"):
                a = [L4.run_day4(t, arm, sc, 30000., L5.day_budget(arm)) for t in book]
                b = [run_day6(t, r6, sc, 30000., budget_of(r6)) for t in book]
                bad = [x["day"] for x, y in zip(a, b) if x["net"] != y["net"] or x["trades"] != y["trades"] or x["spent"] != y["spent"]]
                assert not bad, (name, bk, sc, bad[:3]); n += len(a)
    for name in ("E032_30k", "EN55"):
        for bk, book in B.items():
            w5 = L5.run_wallet(book, L5.ARMS[name]); w6 = run_wallet6(book, ARMS[name])
            assert (w5["P"], w5["swept"], w5["halted"], w5["first_halt"]) == (w6["P"], w6["swept"], w6["halted"], w6["first_halt"]), (name, bk)
    for mode, res in (("legout", 5000.), ("legout", 2500.), ("bracket", 5000.), ("bracket", 2500.)):
        s5 = L5.Straddle(mode, reserve=res); s6 = Pair(mode, reserve=res)
        for bk, book in B.items():
            for sc in ("ordinary", "adverse"):
                a = [L5.straddle_day(t, s5, sc, 30000., res) for t in book]; b = [pair_day(t, s6, sc, 30000., res) for t in book]
                bad = [x["day"] for x, y in zip(a, b) if x["net"] != y["net"] or x["trades"] != y["trades"] or x.get("refusal") != y.get("refusal")]
                assert not bad, (mode, res, bk, sc, bad[:3])
    return f"PARITY_OK {n} arm-days (run_day6 == run_day4), wallets, pair engine == straddle_day"


def check_causal(B):
    """Signals, residual inputs, EN63 picks and the library's decision inputs do not move when every later bar is
    erased, or when only the next bar's option prices change."""
    n = 0
    for bk, book in B.items():
        for t in book[::9]:
            for mode in ("CUSUM", "CUSUM_ORB5", "IMPACT", "IMPACT_RET", "IMPACT_VOL"):
                d0 = setup6(t, mode)[0].copy()
                for i in np.flatnonzero(d0)[:2]:
                    u = _truncated(t, int(i)); assert setup6(u, mode)[0][i] == d0[i], (t.day, mode, int(i)); n += 1
                    v = _fillbar_changed(t, int(i)); assert setup6(v, mode)[0][i] == d0[i]; n += 1
            for r in resid_rows(t)[:3]:
                u = _truncated(t, r["i"]); x = resid_at(u, r["i"], r["j"]); assert x is not None and np.allclose(x, (r["res"], r["dec"])); n += 1
                pick = L4.choose4(L4.spec_of(t), _fillbar_changed(t, r["i"]), r["i"], r["d"], RULE62, 2500., 30000.)
                assert pick and pick[0] == r["j"]; n += 1
            sig = L4.signals(t, E032)[0]
            for i in np.flatnonzero(sig)[:2]:
                sp = L4.spec_of(t); a = liq_pick(sp, t, int(i), int(sig[i]), ARMS["EN63"], 2500., 30000.)
                assert a == liq_pick(sp, _truncated(t, int(i)), int(i), int(sig[i]), ARMS["EN63"], 2500., 30000.); n += 1
    return f"CAUSAL_OK {n} decisions unchanged with later bars erased or the fill bar repriced"


def check_mech():
    """Synthetic mechanics: marked equity, the EN65 bank + child accounting bound, the package floor, perturbations."""
    t = L4._synthetic_tape(np.full(375, 50.), index_step=0.); D = D4._D(); n = 375; i0 = at(t, 780)
    sp = L4.spec_of(t)
    q = np.full((n, 2, 5), np.nan)
    for k in (0, 1):
        q[:, k, 0] = q[:, k, 3] = 15.; q[:, k, 1] = 15.02; q[:, k, 2] = 14.98; q[:, k, 4] = 1e6
    c0 = round(float(t.close[i0]) / 50) * 50

    def tape(qq):
        u = D.Tape(t.day, t.x, t.f, qq, np.array([c0, c0]), np.array([1, -1]), ["C", "P"], t.now, t.minute, 0); KEEP6.append(u); return u
    # package: the call doubles, the put falls to 5.5 -> leg-out (pair about +13% >= 10%), then the call gives back -> PACKAGE_FLOOR
    g = q.copy(); g[i0 + 3:, 0, :4] = 30.; g[i0 + 3:, 1, :4] = 5.5; g[i0 + 9:, 0, :4] = 21.
    r = pair_day(tape(g), Pair("package"), details=True)
    rs = {e["reason"]: e["i"] for e in r["positions"][0]["events"] if e["side"] == "SELL"}
    assert rs.get("LEG_OUT") == i0 + 4 and rs.get("PACKAGE_FLOOR") == i0 + 10, rs
    assert r["marked_worst"] <= 0
    # without the gate the same path legs out at once under EN52 rules
    h = q.copy(); h[i0 + 3:, 0, :4] = 23.; h[i0 + 3:, 1, :4] = 4.
    a = pair_day(tape(h), Pair("package"), details=True); b = pair_day(tape(h), Pair("legout"), details=True)
    assert "LEG_OUT" not in {e.get("reason") for e in a["positions"][0]["events"]} and "LEG_OUT" in {e.get("reason") for e in b["positions"][0]["events"]}
    # perturbations move fills in the stated direction
    with perturb(ticks=2):
        f, p = _exe(sp, tape(q), i0 + 1, 0, "BUY", "ordinary", 1)
    assert p == L4.executable(sp, tape(q), i0 + 1, 0, "BUY", "ordinary", 1)[1] + .10
    with perturb(delay=1):
        assert _exe(sp, tape(q), n - 1, 0, "BUY", "ordinary", 1) == (0, None)
    # marked equity: a bought lot whose bar low collapses marks below zero, then recovers
    pos = dict(j=0, entry_i=10, exit_i=12, events=[dict(i=10, side="BUY", lots=1, price=15., fees=20.), dict(i=12, side="SELL", lots=1, price=15., fees=20.)])
    w = q.copy(); w[11, 0, 2] = 5.
    mw = marked_worst(sp, tape(w), [pos]); assert mw < -(10 * sp.lot) + 1, mw
    return "MECH_OK package floor, EN52 gate, perturbations, marked equity"


def counts(B):
    """Counts only (no rupees): signals, intents, parents, refusals, EN64 coverage, EN62 warm-up, EN59 affordability."""
    out = {}
    for bk, book in B.items():
        prepare62(book)
        c = {}
        for name, arm in ARMS.items():
            if name.startswith("EN57") or name.startswith("EN67_e"):
                continue
            rs = [day6(t, arm, "ordinary", 30000., budget_of(arm), False) for t in book]
            c[name] = dict(intents=int(sum(r.get("intents", 0) for r in rs)), parents=int(sum(r["trades"] for r in rs)),
                           expiries=int(sum(r["trades"] > 0 for r in rs)))
            if isinstance(arm, Pair):
                ref = {}
                for r in rs:
                    ref[r.get("refusal") or "entered"] = ref.get(r.get("refusal") or "entered", 0) + 1
                c[name]["refusals"] = ref
        c["EN64_covered_minutes"] = int(sum(_C.get(("cov", id(t), "IMPACT"), 0) for t in book))
        c["EN62_sessions_with_thresholds"] = int(sum(1 for t in book if RES62[(und(t), t.day)]["thresholds"]))
        out[bk] = c
    return out


def check():
    L5.install(); B = books()
    print(check_parity(B), flush=True)
    print(check_causal(B), flush=True)
    print(check_mech(), flush=True)
    print("COUNTS", json.dumps(counts(B)), flush=True)


if __name__ == "__main__":
    check()
