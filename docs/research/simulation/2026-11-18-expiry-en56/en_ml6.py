"""EN61 (PLAN6.md): observable candidates, quantity-aligned labels, the shallow gradient-boosting payoff model with a
walk-forward temperature, and its four controls (EN49 corrected, aligned 3-minute ridge, aligned 15-minute ridge,
intercept-only). Candidate rows read only bars <= the decision; labels are outcomes and never remove a row.

The executor IS the label policy: next-bar entry under the limit with the actual fill quantity, then the marked
liquidation barriers (-0.25 / +0.50 of the filled reserve, loss checked first inside a bar), else a 15-bar timeout or
the 15:14 flat, sold on a later bar; UNRESOLVED loses the whole premium. Runs in sentinel-ml-venv (scikit-learn 1.5.2)."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib, json, math, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import en_lab6 as L6  # noqa: E402

L5, L4, E = L6.L5, L6.L4, L6.E
SEED = 20261118
CLASSES = ("WIN", "LOSS", "TIMEOUT", "NO_FILL")
FUNDED = ("WIN", "LOSS", "TIMEOUT")
HGB = dict(max_depth=2, max_leaf_nodes=4, max_iter=32, learning_rate=0.05, min_samples_leaf=100, l2_regularization=1.0,
           early_stopping=False, random_state=SEED)


@dataclass(frozen=True)
class ML61:
    model: str = "HGB"            # HGB (primary), R1 (EN49 corrected), R2 (aligned 3-min ridge), R3 (aligned 15-min ridge), R4 (intercept)
    reserve: float = 2500.
    max_intents: int = 3

    @property
    def key(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


ARMS = {"EN61": ML61("HGB"), "EN61_r1_ctl": ML61("R1"), "EN61_r2_ctl": ML61("R2"), "EN61_r3_ctl": ML61("R3"), "EN61_r4_ctl": ML61("R4")}


# ---------------------------------------------------------------- observable candidates (decision-time data only)
def candidates(t):
    sp = L4.spec_of(t); rows = []
    for m in L6.GRID:
        i = L6.at(t, m)
        if i >= t.n - 2 or t.minute[i] != m or i < 21 or not L6.options_at(t, i):
            continue
        for d in (1, -1):
            if not L4._avail(t, i, d):
                continue
            f6 = L5.feat49(t, i, d)
            if f6 is None:
                continue
            pick = L4.choose4(sp, t, i, d, L6.RULE62, 2500., 30000.)
            if not pick:
                continue
            j, lots, limit = pick; cl = float(t.q[i, j, 3]); A = L6.atr(t, i); ask = L4.ask_of(cl)
            f6 = list(f6); f6[4] = 2 * E.half(cl) / ask
            res = L4.reserve(sp, limit, lots); u = lots * sp.lot
            charges = (L4.fee(sp, ask, u, True) + L4.fee(sp, ask, u, False)) / res
            rows.append(dict(i=i, d=d, j=j, lots=lots, limit=limit, reserve=round(res, 2), x6=f6,
                             x8=f6 + [charges, d * (float(t.strikes[j]) - float(t.close[i])) / A]))
    return rows


# ---------------------------------------------------------------- executors / labels
def _sell_from(sp, t, b, j, f, scenario):
    for k in range(b, t.n):
        fs, p2 = L6._exe(sp, t, k, j, "SELL", scenario, f)
        if fs:
            return k, p2
    return None


def exec15(t, c, scenario="ordinary", lots=None, limit=None):
    """The primary's executor and label. Returns dict(cls, y, net, Rc, events, entry_i, exit_i, j)."""
    sp = L4.spec_of(t); LOT = sp.lot; i, j = c["i"], c["j"]; lots = c["lots"] if lots is None else lots; limit = c["limit"] if limit is None else limit
    f, p = L6._exe(sp, t, i + 1, j, "BUY", scenario, lots)
    if not f or p is None or p > limit:
        return dict(cls="NO_FILL", y=0., net=0., Rc=0.)
    u = f * LOT; buy = p * u; bf = L4.fee(sp, p, u, True); Rc = L4.reserve(sp, p, f); trig = None
    for b in range(i + 1, t.n - 1):
        r = t.q[b, j]
        if np.isfinite(r).all():
            lo, hi = L4.bid_of(r[2]), L4.bid_of(r[1])
            if lo * u - L4.fee(sp, lo, u, False) - buy - bf <= -.25 * Rc:
                trig = ("LOSS", b); break
            if hi * u - L4.fee(sp, hi, u, False) - buy - bf >= .5 * Rc:
                trig = ("WIN", b); break
        if b - (i + 1) >= 14 or t.minute[b] >= 914:
            trig = ("TIMEOUT", b); break
    ev = [dict(i=i + 1, decision_i=i, side="BUY", lots=f, price=p, fees=bf)]
    sale = _sell_from(sp, t, trig[1] + 1, j, f, scenario) if trig else None
    if sale is None:
        return dict(cls="LOSS", y=-(buy + bf) / Rc, net=round(-buy - bf, 2), Rc=Rc, events=ev, entry_i=i + 1, exit_i=t.n - 1, j=j, lots=f,
                    unresolved=1, reason="UNRESOLVED")
    k, p2 = sale; sf = L4.fee(sp, p2, u, False); net = (p2 - p) * u - bf - sf
    ev.append(dict(i=k, decision_i=trig[1], side="SELL", lots=f, price=p2, fees=sf, reason=trig[0]))
    return dict(cls=trig[0], y=net / Rc, net=round(net, 2), Rc=Rc, events=ev, entry_i=i + 1, exit_i=k, j=j, lots=f, unresolved=0, reason=trig[0])


def exec3(t, c, scenario="ordinary", one_lot=False, lots=None, limit=None):
    """3-minute executor: next-bar entry, sale at decision + 4 (retried later); R1 = one lot, R2 = actual lots."""
    sp = L4.spec_of(t); LOT = sp.lot; i, j = c["i"], c["j"]
    lots = 1 if one_lot else (c["lots"] if lots is None else lots); limit = c["limit"] if limit is None else limit
    f, p = L6._exe(sp, t, i + 1, j, "BUY", scenario, lots)
    if not f or p is None or p > limit:
        return dict(cls="NO_FILL", y=0., net=0., Rc=0.)
    u = f * LOT; buy = p * u; bf = L4.fee(sp, p, u, True); Rc = L4.reserve(sp, p, f)
    ev = [dict(i=i + 1, decision_i=i, side="BUY", lots=f, price=p, fees=bf)]
    sale = _sell_from(sp, t, i + 4, j, f, scenario)
    if sale is None:
        return dict(cls="LOSS", y=-(buy + bf) / Rc, net=round(-buy - bf, 2), Rc=Rc, events=ev, entry_i=i + 1, exit_i=t.n - 1, j=j, lots=f,
                    unresolved=1, reason="UNRESOLVED")
    k, p2 = sale; sf = L4.fee(sp, p2, u, False); net = (p2 - p) * u - bf - sf
    ev.append(dict(i=k, decision_i=i + 3, side="SELL", lots=f, price=p2, fees=sf, reason="TIME"))
    return dict(cls="TIMEOUT", y=net / Rc, net=round(net, 2), Rc=Rc, events=ev, entry_i=i + 1, exit_i=k, j=j, lots=f, unresolved=0, reason="TIME")


def labels(t, rows):
    """Ordinary-fill labels for every observable row: the 15-bar class / y, the aligned 3-minute y, the one-lot y
    (EN49 corrected: NO_FILL rows stay, label 0)."""
    sp = L4.spec_of(t)
    for c in rows:
        a = exec15(t, c); c["cls"] = a["cls"]; c["y15"] = a["y"]
        b = exec3(t, c); c["y3"] = b["y"]
        r1 = exec3(t, c, one_lot=True)
        res1 = L4.reserve(sp, c["limit"], 1)
        c["y1"] = (r1["net"] / res1) if r1["cls"] != "NO_FILL" else 0.
    return rows


# ---------------------------------------------------------------- the model and its calibration
def _temp(P, ycls):
    """Golden-section on log T in [log 0.1, log 10] for the mean log loss of softmax(log P / T)."""
    L = np.log(np.clip(P, 1e-12, 1.)); idx = ycls

    def loss(lt):
        T = math.exp(lt); Z = L / T; Z = Z - Z.max(1, keepdims=True); Q = np.exp(Z); Q /= Q.sum(1, keepdims=True)
        return float(-np.mean(np.log(np.clip(Q[np.arange(len(idx)), idx], 1e-12, 1.))))
    a, b = math.log(.1), math.log(10.); g = (math.sqrt(5) - 1) / 2
    c, d = b - g * (b - a), a + g * (b - a)
    for _ in range(60):
        if loss(c) < loss(d):
            b = d
        else:
            a = c
        c, d = b - g * (b - a), a + g * (b - a)
    return math.exp((a + b) / 2)


def _soft(P, T):
    Z = np.log(np.clip(P, 1e-12, 1.)) / T; Z = Z - Z.max(1, keepdims=True); Q = np.exp(Z)
    return Q / Q.sum(1, keepdims=True)


def walk(book, verbose=False):
    """Walk-forward per index. Returns {model: {day: [(i, d, row, E, threshold)] chosen decisions}}, plus a log of
    abstentions, temperatures and calibration diagnostics."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    S = []
    for t in book:
        S.append((t, labels(t, candidates(t))))
    out = {m: {} for m in ("HGB", "R1", "R2", "R3", "R4")}; log = []
    for s, (t, rows) in enumerate(S):
        train = S[:max(0, s - 10)]; calib = S[max(0, s - 10):s]
        tr = [r for _, rs in train for r in rs]; ca = [r for _, rs in calib for r in rs]
        why = None
        if len(train) < 40:
            why = "train_sessions"
        elif len(calib) < 10:
            why = "calib_sessions"
        elif len(tr) < 500:
            why = "train_rows"
        rec = dict(day=t.day, train_sessions=len(train), train_rows=len(tr), calib_rows=len(ca), rows=len(rows))
        if why:
            rec["abstain"] = why; log.append(rec)
            for m in out:
                out[m][t.day] = []
            continue
        # payoffs and support from the calibration sample (normalised realised net of each funded class)
        pay = {k: [r["y15"] for r in ca if r["cls"] == k] for k in FUNDED}
        rec["calib_counts"] = {k: len(v) for k, v in pay.items()}; rec["calib_nofill"] = sum(r["cls"] == "NO_FILL" for r in ca)
        payoff = {k: (float(np.mean(v)) if v else 0.) for k, v in pay.items()}; payoff["NO_FILL"] = 0.
        rec["payoff"] = {k: round(v, 4) for k, v in payoff.items()}
        Xtr = np.array([r["x8"] for r in tr], float); ytr = np.array([CLASSES.index(r["cls"]) for r in tr])
        present = sorted(set(ytr.tolist()))
        clf = HistGradientBoostingClassifier(**HGB).fit(Xtr, ytr)
        Pca = clf.predict_proba(np.array([r["x8"] for r in ca], float)) if ca else np.zeros((0, len(present)))
        yca = np.array([present.index(CLASSES.index(r["cls"])) if CLASSES.index(r["cls"]) in present else -1 for r in ca])
        keep = yca >= 0
        T = _temp(Pca[keep], yca[keep]) if keep.sum() >= 10 else 1.
        rec["T"] = round(T, 4); rec["present"] = [CLASSES[k] for k in present]
        Pc = _soft(Pca, T) if len(ca) else Pca
        rec["calib_logloss_model"] = round(float(-np.mean(np.log(np.clip(Pc[np.flatnonzero(keep), yca[keep]], 1e-12, 1)))), 4) if keep.sum() else None
        freq = np.bincount(ytr, minlength=4)[present] / len(ytr)
        rec["calib_logloss_icpt"] = round(float(-np.mean(np.log(np.clip(freq[yca[keep]], 1e-12, 1)))), 4) if keep.sum() else None
        short = [k for k in FUNDED if CLASSES.index(k) in present and len(pay[k]) < 20]
        hgb_ok = not short
        if short:
            rec["abstain_hgb"] = "calib_class_support:" + ",".join(short)
        P = _soft(clf.predict_proba(np.array([r["x8"] for r in rows], float)), T) if rows else np.zeros((0, len(present)))
        # ridge controls on the same training set
        def ridge(xkey, ykey):
            stats = []
            for _, rs in train:
                if rs:
                    stats.append(L5.ridge_stats(np.array([r[xkey] for r in rs], float), np.array([r[ykey] for r in rs], float)))
            return stats
        st1, st2, st3 = ridge("x6", "y1"), ridge("x8", "y3"), ridge("x8", "y15")
        f1, f2, f3 = L5.ridge_fit(st1), L5.ridge_fit(st2), L5.ridge_fit(st3); b1 = L5.boot_fits(st1)
        prior = {k: float(np.mean(ytr == CLASSES.index(k))) for k in CLASSES}
        E4 = sum(prior[k] * payoff[k] for k in CLASSES)
        rec["E_icpt"] = round(E4, 4)
        by_i = {}
        for n, r in enumerate(rows):
            by_i.setdefault(r["i"], []).append((n, r))
        picks = {m: [] for m in out}
        for i, rs in sorted(by_i.items()):
            best = {m: None for m in out}
            for n, r in rs:
                th = L4.spec_of(t).order / r["reserve"]
                eh = float(sum(P[n, a] * payoff[CLASSES[k]] for a, k in enumerate(present)))
                r["E_hgb"] = eh
                L6.DIAG61.append((L6.und(t), t.day, eh, r["y15"], r["cls"]))
                cand = {"HGB": (eh, th) if hgb_ok else None, "R2": (L5.ridge_pred(f2, r["x8"]), th), "R3": (L5.ridge_pred(f3, r["x8"]), th),
                        "R4": (E4, th) if hgb_ok else None}
                mu1 = L5.ridge_pred(f1, r["x6"]); p5 = float(np.percentile([L5.ridge_pred(b, r["x6"]) for b in b1], 5))
                cand["R1"] = (mu1, 0.) if p5 > 0 else None
                for m, v in cand.items():
                    if v is not None and v[0] > v[1] and (best[m] is None or v[0] > best[m][3]):
                        best[m] = (i, r["d"], r, v[0], v[1])
            for m in out:
                if best[m]:
                    picks[m].append(best[m])
        for m in out:
            out[m][t.day] = picks[m]
        rec["max_E_hgb"] = round(max([r.get("E_hgb", -9) for r in rows], default=-9), 4)
        log.append(rec)
        if verbose:
            print(t.day, rec.get("abstain_hgb", ""), rec["T"], flush=True)
    return out, log, S


DEC = {}                         # (und, model) -> {day: [(i, d, row, E, th)]}


def day61(t, arm, scenario="ordinary", cash=30000., budget=None, details=False):
    """One parent per expiry: the first chosen decision, then (on NO_FILL) the next, at most 3 intents."""
    sp = L4.spec_of(t); budget = arm.reserve if budget is None else budget
    picks = DEC.get((L6.und(t), arm.model), {}).get(t.day, [])
    base = dict(day=t.day, net=0., trades=0, spent=0., fees=0., unresolved=0, rejected=0, positions=[], marked_worst=0., calm=False,
                missed=[], intents=0)
    room = min(arm.reserve, budget, cash)
    for n, (i, d, r, Ev, th) in enumerate(picks[:arm.max_intents]):
        lots, limit = r["lots"], r["limit"]
        if r["reserve"] > room + .01:
            pk = L4.choose4(sp, t, i, d, L6.RULE62, room, cash)
            if not pk or pk[0] != r["j"]:
                base["intents"] += 1; base["rejected"] += 1; continue
            lots, limit = pk[1], pk[2]
        base["intents"] += 1
        if arm.model == "R1":
            a = exec3(t, r, scenario, one_lot=True)
        elif arm.model == "R2":
            a = exec3(t, r, scenario, lots=lots, limit=limit)
        else:
            a = exec15(t, r, scenario, lots=lots, limit=limit)
        if a["cls"] == "NO_FILL":
            base["rejected"] += 1; continue
        fees = sum(e["fees"] for e in a["events"])
        pos = dict(day=t.day, j=a["j"], symbol=t.symbols[a["j"]], direction=d, entry_i=a["entry_i"], decision_i=i, exit_i=a["exit_i"],
                   lots=a["lots"], entry=a["events"][0]["price"], net=a["net"], fees=round(fees, 2), origin=f"EN61_{arm.model}",
                   events=a["events"], unresolved=bool(a["unresolved"]), first=a["events"][0]["price"], cls=a["cls"], E=Ev)
        mw = L6.marked_worst(sp, t, [pos])
        spent = L4.reserve(sp, pos["entry"], pos["lots"])
        assert spent <= room + .01 and pos["net"] >= -spent - .03
        return dict(base, net=a["net"], trades=1, spent=round(spent, 2), fees=round(fees, 2), unresolved=a["unresolved"],
                    positions=[pos] if details else [], marked_worst=mw)
    return base


L6.DAYFN[ML61] = day61
L6.DIAG61 = []


def prepare(B, verbose=False):
    logs = {}
    for name, book in B.items():
        out, log, _ = walk(book, verbose)
        for m, v in out.items():
            DEC[(name, m)] = v
        logs[name] = log
    return logs
