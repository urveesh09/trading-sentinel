"""Round 5b (PLAN5B.md): EN41 / EN42 on TR01 order-book packets and the Q28 resting-bid fill check, NIFTY Nov 17 2026.

    python en5b.py selftest   whole pipeline on 13:00-13:40 only; nothing written, no rupees printed
    python en5b.py freeze     hashes plan, code, fee modules and the export manifests -> freeze5b.json
    python en5b.py score      refuses unless the freeze is committed and unchanged; start receipt; results5b.json once
Times are IST seconds since midnight, by receipt. Prices from walked 5-level depth; NFO fees per fill."""
from __future__ import annotations
import hashlib, json, math, random, statistics as st, subprocess, sys, time
from pathlib import Path
import numpy as np
import tr01
import en_lab5 as L5

L4 = L5.L4; SP = L4.NIFTY
HERE = Path(__file__).resolve().parent
DAY = "2026-11-17"; T0 = 9 * 3600 + 15 * 60; NW = 2250; TICK = .1
DEC0, DEC1, FLAT, LAST = 9 * 3600 + 45 * 60, 14 * 3600 + 45 * 60, 15 * 3600 + 14 * 60, 15 * 3600 + 29 * 60
FILES = ("PLAN5B.md", "tr01.py", "en5b.py", "en_lab5.py")
EXTERNAL = {"en_lab4.py": HERE.parent / "2026-11-17-expiry-en/en_lab4.py", "e02_lab.py": HERE.parent / "2026-11-03-expiry-e02/e02_lab.py",
            "expiry_paper.py": HERE.parents[3] / "python-engine/expiry_paper.py", "cost_schedules.py": HERE.parents[3] / "python-engine/cost_schedules.py"}
RESULTS, START, FREEZE = HERE / "results5b.json", HERE / "results5b-started.json", HERE / "freeze5b.json"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git(*a):
    return subprocess.run(("git",) + a, cwd=HERE, capture_output=True, text=True).stdout.strip()


# ---------------------------------------------------------------- data
class Day:
    def __init__(self, day=DAY):
        ins = tr01.instruments(day)
        fut = sorted((r for r in ins if r["underlying"] == "NIFTY" and r["type"] == "FUT"), key=lambda r: r["expiry"])[0]
        self.opts = {r["token"]: r for r in ins if r["underlying"] == "NIFTY" and r["type"] in ("CE", "PE") and r["expiry"] == day}
        D = tr01.extract(day, [fut["token"], 256265] + list(self.opts))
        f = D[fut["token"]]; self.fs = tr01.ist_seconds(f["recv"])
        self.fb, self.fbq, self.fa, self.faq = f["bp"][:, 0], f["bq"][:, 0], f["ap"][:, 0], f["aq"][:, 0]
        self.mid = (self.fb + self.fa) / 2
        ix = D[256265]; self.is_, self.il = tr01.ist_seconds(ix["recv"]), ix["ltp"]
        self.o = {}
        for tok, r in self.opts.items():
            if tok in D:
                a = D[tok]; self.o[tok] = dict(s=tr01.ist_seconds(a["recv"]), bp=a["bp"], bq=a["bq"], ap=a["ap"], aq=a["aq"], ltp=a["ltp"],
                                               vol=a["vol"], K=float(r["strike"]), d=1 if r["type"] == "CE" else -1)
        self.fbars = self._bars(self.fs, self.mid); self.ibars = self._bars(self.is_, self.il)
        self._windows()

    @staticmethod
    def _bars(s, v):
        m = np.floor(s / 60).astype(int); out = {}
        for k in np.unique(m):
            x = v[m == k]; x = x[np.isfinite(x)]
            if len(x):
                out[int(k)] = (float(x.max()), float(x.min()), float(x[-1]))
        return out

    def atr(self, bars, t):
        m = int(t // 60); tr = []
        for j in range(m - 10, m):
            if j not in bars or j - 1 not in bars:
                return math.nan
            h, l, _ = bars[j]; pc = bars[j - 1][2]; tr.append(max(h - l, abs(h - pc), abs(l - pc)))
        return float(np.mean(tr))

    def last(self, s, t):
        return int(np.searchsorted(s, t, side="right")) - 1

    def mid_at(self, t):
        i = self.last(self.fs, t)
        return float(self.mid[i]) if i >= 0 else math.nan

    def _windows(self):
        b, qb, a, qa = self.fb, self.fbq, self.fa, self.faq
        e = np.zeros(len(b))
        e[1:] = ((b[1:] >= b[:-1]) * qb[1:] - (b[1:] <= b[:-1]) * qb[:-1] - (a[1:] <= a[:-1]) * qa[1:] + (a[1:] >= a[:-1]) * qa[:-1])
        self.ofi = np.full(NW, np.nan); self.valid = np.zeros(NW, bool); self.mclose = np.full(NW, np.nan); self.mopen = np.full(NW, np.nan)
        for k in range(NW):
            lo, hi = T0 + 10 * k, T0 + 10 * k + 10
            i0, i1 = int(np.searchsorted(self.fs, lo)), int(np.searchsorted(self.fs, hi))
            j = self.last(self.fs, lo - 1e-9)
            self.mopen[k] = self.mid[j] if j >= 0 else (self.mid[i0] if i0 < len(self.mid) else np.nan)
            if i1 > i0:
                top = float(np.mean((qb[i0:i1] + qa[i0:i1]) / 2))
                self.ofi[k] = float(e[i0:i1].sum()) / top if top > 0 else np.nan
                self.mclose[k] = self.mid[i1 - 1]
                occ = len(np.unique(np.floor(self.fs[i0:i1]).astype(int)))
                self.valid[k] = occ >= 8 and hi - self.fs[i1 - 1] <= 2
        self.z = np.full(NW, np.nan)
        for k in range(60, NW):
            ref = self.ofi[k - 60:k][self.valid[k - 60:k]]
            if len(ref) >= 30 and np.std(ref) > 0 and self.valid[k]:
                self.z[k] = (self.ofi[k] - np.mean(ref)) / np.std(ref)

    def wend(self, k):
        return T0 + 10 * k + 10


# ---------------------------------------------------------------- signals
def en41_events(D):
    ev = []
    for k in range(61, NW):
        t = D.wend(k)
        if not DEC0 <= t <= DEC1 or not (D.valid[k - 1] and D.valid[k]) or not np.isfinite([D.z[k - 1], D.z[k]]).all():
            continue
        d = int(np.sign(D.z[k]))
        if d == 0 or np.sign(D.z[k - 1]) != d or min(abs(D.z[k - 1]), abs(D.z[k])) < 2:
            continue
        A = D.atr(D.fbars, t); mv = d * (D.mclose[k] - D.mopen[k - 1])
        if np.isfinite(A) and .10 * A <= mv <= .50 * A:
            ev.append(dict(t=t, d=d, k=k, A=A, kind="EN41"))
    return ev


def progress_events(D):
    ev = []
    for k in range(61, NW):
        t = D.wend(k)
        if not DEC0 <= t <= DEC1 or not (D.valid[k - 1] and D.valid[k]):
            continue
        A = D.atr(D.fbars, t); mv = D.mclose[k] - D.mopen[k - 1]
        if np.isfinite(A) and .10 * A <= abs(mv) <= .50 * A:
            ev.append(dict(t=t, d=int(np.sign(mv)), k=k, A=A, kind="PROGRESS"))
    return ev


def en42_events(D, fade=False):
    ev = []; used = set()
    for k in range(61, NW - 3):
        t = D.wend(k)
        if not DEC0 <= t <= DEC1 or not (D.valid[k - 1] and D.valid[k]) or not np.isfinite([D.z[k - 1], D.z[k]]).all():
            continue
        d = int(np.sign(D.z[k]))
        if d == 0 or np.sign(D.z[k - 1]) != d or min(abs(D.z[k - 1]), abs(D.z[k])) < 2:
            continue
        A = D.atr(D.fbars, t)
        if not np.isfinite(A) or abs(D.mclose[k] - D.mopen[k - 1]) > .10 * A:
            continue
        lo_t, hi_t = T0 + 10 * (k - 1), t
        i0, i1 = int(np.searchsorted(D.fs, lo_t)), int(np.searchsorted(D.fs, hi_t))
        if i1 - i0 < 4:
            continue
        side_p, side_q = (D.fa, D.faq) if d > 0 else (D.fb, D.fbq)
        ref = side_p[i0]; rep = sum(1 for n in range(i0 + 1, i1) if abs(side_p[n] - ref) <= 2 * TICK + 1e-9 and side_q[n] > side_q[n - 1])
        if rep < 3 or k in used:
            continue
        hi, lo = float(np.nanmax(D.mid[i0:i1])), float(np.nanmin(D.mid[i0:i1]))
        used.add(k); s = -d
        if fade:
            ev.append(dict(t=t, d=s, k=k, A=A, hi=hi, lo=lo, kind="FADE")); continue
        for j in range(k + 1, k + 4):
            if not D.valid[j] or not np.isfinite(D.ofi[j]):
                continue
            brk = D.mclose[j] < lo - TICK if d > 0 else D.mclose[j] > hi + TICK
            if brk and np.sign(D.ofi[j]) == -d and D.wend(j) <= DEC1:
                ev.append(dict(t=D.wend(j), d=s, k=j, A=A, hi=hi, lo=lo, kind="EN42")); break
    return ev


# ---------------------------------------------------------------- execution on real depth
def walk(prices, qtys, units):
    left, cost = units, 0.
    for p, q in zip(prices, qtys):
        if not np.isfinite(p) or q <= 0 or left <= 0:
            continue
        take = min(left, int(q)); cost += take * p; left -= take
    return None if left > 0 else cost / units


def pick(D, t, d, room=1250.):
    i = D.last(D.is_, t)
    if i < 0 or t - D.is_[i] > 2:
        return None
    S = float(D.il[i]); A = D.atr(D.ibars, t)
    if not np.isfinite(A):
        return None
    cap = min(200., 1.0 * A * math.sqrt(max(1., 930 - t / 60)))
    cands = sorted((o for o in D.o.items() if o[1]["d"] == d and 0 < d * (o[1]["K"] - S) <= cap), key=lambda o: d * o[1]["K"])
    for tok, o in cands:
        j = D.last(o["s"], t)
        if j < 0 or t - o["s"][j] > 2 or not 5. <= o["ap"][j, 0] <= 20.:
            continue
        for n in (3, 2, 1):
            wa = walk(o["ap"][j], o["aq"][j], n * SP.lot)
            if wa is None:
                continue
            limit = math.floor(round(wa * 1.04 / .05, 6)) * .05
            if limit * n * SP.lot + L4.fee(SP, limit, n * SP.lot, True) + n * SP.order <= room + 1e-9:
                return tok, n, round(limit, 2)
    return None


def buy(D, tok, n, limit, t, delta):
    o = D.o[tok]; units = n * SP.lot
    for j in range(int(np.searchsorted(o["s"], t + delta)), len(o["s"])):
        if o["s"][j] > t + 20:
            break
        wa = walk(o["ap"][j], o["aq"][j], units)
        if wa is not None and wa <= limit + 1e-9:
            return float(o["s"][j]), wa
    return None


def sell(D, tok, n, t, delta):
    o = D.o[tok]; units = n * SP.lot
    for j in range(int(np.searchsorted(o["s"], t + delta)), len(o["s"])):
        if o["s"][j] > LAST:
            break
        wb = walk(o["bp"][j], o["bq"][j], units)
        if wb is not None:
            return float(o["s"][j]), wb
    return None


def exit_trigger(D, ev, tok, entry, ft):
    o = D.o[tok]; d = ev["d"]; m0 = D.mid_at(ft); A = ev["A"]
    for t in range(int(math.ceil(ft)) + 1, int(min(ft + 180, FLAT)) + 1):
        j = D.last(o["s"], t)
        if j >= 0 and t - o["s"][j] <= 2 and np.isfinite(o["bp"][j, 0]) and o["bp"][j, 0] <= .65 * entry:
            return t, "STOP"
        m = D.mid_at(t)
        if ev["kind"] in ("EN42", "FADE"):
            if (d < 0 and m > ev["hi"] + .10 * A) or (d > 0 and m < ev["lo"] - .10 * A):
                return t, "EPISODE_BREAK"
            if d * (m - m0) >= .75 * A:
                return t, "TARGET"
        else:
            if d * (m - m0) <= -.50 * A:
                return t, "ADVERSE"
            if (t - T0) % 10 == 0:
                k = (t - T0) // 10 - 1
                if k >= 1 and T0 + 10 * (k - 1) >= ft and np.isfinite([D.ofi[k], D.ofi[k - 1]]).all() \
                        and np.sign(D.ofi[k]) == -d and np.sign(D.ofi[k - 1]) == -d:
                    return t, "OFI_REVERSED"
    return (int(min(ft + 180, FLAT)), "CLOCK" if ft + 180 <= FLAT else "FLAT")


def book(D, events, delta, side_of=None):
    """One open position at a time, at most two parents, Rs 2,500 a day; events in time order."""
    out = []; busy = -1.; spent = 0.
    for ev in sorted(events, key=lambda e: e["t"]):
        if len(out) >= 2 or ev["t"] < busy:
            continue
        ev = dict(ev, d=side_of(ev) if side_of else ev["d"])
        p = pick(D, ev["t"], ev["d"], min(1250., 2500. - spent))
        if not p:
            continue
        tok, n, limit = p; f = buy(D, tok, n, limit, ev["t"], delta)
        if not f:
            out.append(dict(t=ev["t"], d=ev["d"], status="MISSED")); continue
        ft, px = f; units = n * SP.lot; spent += limit * units + L4.fee(SP, limit, units, True) + n * SP.order
        tt, why = exit_trigger(D, ev, tok, px, ft); s = sell(D, tok, n, tt, delta)
        if s:
            st_, sp_ = s; net = (sp_ - px) * units - L4.fee(SP, px, units, True) - L4.fee(SP, sp_, units, False); busy = st_
        else:
            net = -(px * units + L4.fee(SP, px, units, True) + n * SP.order); busy = LAST; why += "+UNRESOLVED"
        out.append(dict(t=ev["t"], d=ev["d"], status="FILLED", strike=D.o[tok]["K"], lots=n, entry=round(px, 2), exit_reason=why,
                        exit=round(sp_, 2) if s else None, hold_s=round((busy - ft), 1), net=round(net, 2)))
    filled = [x for x in out if x["status"] == "FILLED"]
    return dict(tickets=len(filled), missed=sum(x["status"] == "MISSED" for x in out), net=round(sum(x["net"] for x in filled), 2),
                winners=sum(x["net"] > 0 for x in filled), trades=out)


def mechanism(D, events):
    out = {}
    for h in (30, 60, 180):
        v = [ev["d"] * (D.mid_at(ev["t"] + h) - D.mid_at(ev["t"])) / TICK for ev in events if ev["t"] + h <= LAST]
        v = [x for x in v if np.isfinite(x)]
        out[f"{h}s"] = dict(n=len(v), mean_ticks=round(float(np.mean(v)), 3) if v else None,
                            t=round(float(np.mean(v) / (np.std(v) / math.sqrt(len(v)))), 2) if len(v) > 2 and np.std(v) > 0 else None)
    return out


# ---------------------------------------------------------------- Q28: do resting bids fill?
def q28(D, t_from=13 * 3600, t_to=15 * 3600):
    rows = []
    for t in range(t_from, t_to, 60):
        i = D.last(D.is_, t)
        if i < 0:
            continue
        S = float(D.il[i])
        for d in (1, -1):
            c = sorted((o for o in D.o.values() if o["d"] == d and 0 < d * (o["K"] - S) <= 200), key=lambda o: d * o["K"])
            o = None
            for x in c:
                j = D.last(x["s"], t)
                if j >= 0 and t - x["s"][j] <= 2 and 5. <= x["ap"][j, 0] <= 20.:
                    o = x; break
            if o is None:
                continue
            B0, Q0 = float(o["bp"][j, 0]), int(o["bq"][j, 0]); m0 = (o["bp"][j, 0] + o["ap"][j, 0]) / 2
            res = {}
            for H in (10, 60):
                k0, k1 = j + 1, int(np.searchsorted(o["s"], t + H, side="right"))
                cum = 0; cons = opt = False
                for k in range(k0, k1):
                    inc = int(o["vol"][k] - o["vol"][k - 1])
                    if o["ltp"][k] <= B0 + 1e-9 and inc > 0:
                        cum += inc
                    cons = cons or cum >= Q0 + SP.lot
                    opt = opt or (np.isfinite(o["ap"][k, 0]) and o["ap"][k, 0] <= B0 + 1e-9) or o["ltp"][k] <= B0 - .05 + 1e-9
                res[H] = (cons, opt)
            w = (o["s"] >= t) & (o["s"] < t + 60)
            proxy = bool(w.any() and float(np.min(o["ltp"][w])) <= B0 - .05 + 1e-9)
            k60 = D.last(o["s"], t + 60)
            m60 = (o["bp"][k60, 0] + o["ap"][k60, 0]) / 2 if k60 >= 0 else np.nan
            rows.append(dict(t=t, d=d, B0=B0, Q0=Q0, cons10=res[10][0], opt10=res[10][1], cons60=res[60][0], opt60=res[60][1], proxy=proxy,
                             move60=float((m60 - B0) / B0) if np.isfinite(m60) else np.nan, m0=float(m0)))
    n = len(rows)
    rate = lambda k: round(sum(r[k] for r in rows) / n, 4) if n else None  # noqa: E731
    adv = lambda flag: round(float(np.nanmean([r["move60"] for r in rows if r["cons60"] == flag])), 4) if any(r["cons60"] == flag for r in rows) else None  # noqa: E731
    agree = sum(r["proxy"] == r["cons60"] for r in rows)
    return dict(orders=n, conservative_10s=rate("cons10"), optimistic_10s=rate("opt10"), conservative_60s=rate("cons60"), optimistic_60s=rate("opt60"),
                minute_proxy=rate("proxy"), proxy_agrees_with_conservative_60s=round(agree / n, 4) if n else None,
                proxy_fills_conservative_misses=sum(r["proxy"] and not r["cons60"] for r in rows),
                median_queue_ahead_lots=round(float(np.median([r["Q0"] for r in rows])) / SP.lot, 1) if n else None,
                mid_move_60s_after_filled=adv(True), mid_move_60s_after_unfilled=adv(False))


# ---------------------------------------------------------------- pipeline
def pipeline(window=None, seeds=40):
    D = Day()
    if window:
        global DEC0, DEC1
        DEC0, DEC1 = window
    e41, e42, prog, fade = en41_events(D), en42_events(D), progress_events(D), en42_events(D, fade=True)
    res = dict(day=DAY, eligible_sessions=[DAY], excluded_sessions={"2026-11-16": "front-future occupied one-second bins 75.9% < 80%"},
               valid_windows=int(D.valid.sum()), events=dict(EN41=len(e41), EN42=len(e42), progress=len(prog), fade=len(fade)))
    for name, ev in (("EN41", e41), ("EN42", e42), ("EN41_progress_only_diag", prog), ("EN42_fade_diag", fade)):
        res[name] = {f"delta_{dl}s": book(D, ev, dl) for dl in (1, 3, 10)}
    res["EN41_delayed_diag"] = {"delta_1s": book(D, [dict(e, t=e["t"] + 10) for e in e41], 1)}
    for name, ev in (("EN41_random_side_diag", e41), ("EN42_random_side_diag", e42)):
        nets = []
        for s in range(seeds):
            rng = random.Random(f"en5b-{name}-{s}")
            nets.append(book(D, ev, 1, side_of=lambda e, r=rng: r.choice((1, -1)))["net"])
        res[name] = dict(median_net=round(st.median(nets), 2) if nets else None, seeds=seeds)
    allw = [dict(t=D.wend(k), d=int(np.sign(D.ofi[k]))) for k in range(61, NW) if D.valid[k] and np.isfinite(D.ofi[k]) and D.ofi[k] != 0
            and DEC0 <= D.wend(k) <= DEC1]
    res["mechanism"] = dict(EN41=mechanism(D, e41), EN42=mechanism(D, e42), progress_only=mechanism(D, prog),
                            all_valid_windows_ofi_sign=mechanism(D, allw))
    res["Q28"] = q28(D)
    res["status"] = dict(EN41="INCONCLUSIVE (one eligible expiry session; support floor 30 tickets on 20 expiries)",
                         EN42="INCONCLUSIVE (one eligible expiry session; support floor 30 tickets on 20 expiries)", Q28="MEASUREMENT")
    return res


def freeze():
    assert not RESULTS.exists() and not START.exists()
    v = tr01.verify()
    FREEZE.write_text(json.dumps(dict(files={**{f: sha(HERE / f) for f in FILES}, **{k: sha(p) for k, p in EXTERNAL.items()}},
                                      export=v, head=git("rev-parse", "HEAD")), indent=2) + "\n")
    print("FROZEN", git("rev-parse", "HEAD"))


def score():
    fz = json.loads(FREEZE.read_text())
    assert all(sha(HERE / f) == h for f, h in fz["files"].items() if f in FILES), "frozen files changed"
    assert all(sha(p) == fz["files"][k] for k, p in EXTERNAL.items()), "frozen dependency changed"
    assert tr01.verify() == fz["export"], "export changed"
    assert not git("status", "--porcelain", "--", *FILES, "freeze5b.json"), "freeze not committed"
    assert not RESULTS.exists() and not START.exists(), "scored once"
    START.write_text(json.dumps(dict(started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), freeze_head=fz["head"]), indent=2) + "\n")
    res = pipeline(); res["freeze_head"] = fz["head"]
    RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8")
    print("DONE", res["status"])


def selftest():
    res = pipeline(window=(13 * 3600, 13 * 3600 + 40 * 60), seeds=2)
    json.dumps(res, default=str)
    print("SELFTEST_OK events", res["events"], "valid windows", res["valid_windows"], "Q28 orders", res["Q28"]["orders"])


if __name__ == "__main__":
    {"freeze": freeze, "score": score, "selftest": selftest}[sys.argv[1]]()
