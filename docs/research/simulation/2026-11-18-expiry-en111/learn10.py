"""EN118 supported action values and EN120 interpretable controller (IMPL10.md sections 4.8, 4.10, 4.11).

Labels are simulator counterfactuals: each (event, action) is replayed alone through run_day10 (Rs 30,000 cash, Rs 2,500
room). Fits read only dates before the fit date. Policies are written as t.sig9/t.meta9 arrays for the shared day loop, so
the book's real room, intents, parents, cooldown and wallet apply to whatever the policy chooses.
"""
import hashlib, json, math
import numpy as np
import round10  # noqa: F401
from data8 import L7
import signals9 as S9
import families9 as F9
import lab10, features10 as FX, families10 as FM
L4 = L7.L4
ACTIONS = ("CASH", "LEGACY_100_8", "NEARER_100_8", "NEARER_150_12", "RANGE")
TREND = ("LEGACY_100_8", "NEARER_100_8", "NEARER_150_12")
PROF = {"LEGACY_100_8": (), "NEARER_100_8": FM.NEAR1, "NEARER_150_12": FM.JOINT, "RANGE": FM.RANGE_KW + (("cov10", 2.),)}
PROFILES120 = {"EN87": "LEGACY_100_8", "EN111": "NEARER_150_12", "EN117": "RANGE"}
RANGE_DEFAULT = (.25, "MIDPOINT", .5)
BOOT = 200
LBL = "LABEL10"


# ------------------------------------------------------------------ opportunity universe and features
def events(t):
    """Flat-book opportunities: E03_env signal minutes and EN117 default range rejections (deduplicated by minute/setup)."""
    out = []
    win = S9.window(t, 870); g = FM.en87_dirs(t)
    for i in np.flatnonzero((t.e03 != 0) & win):
        i = int(i); d = int(t.e03[i])
        if not np.isfinite(t.close[i]) or not L4._avail(t, i, d):
            continue
        out.append(dict(i=i, d=d, setup="E03", en87=bool(g[i] != 0)))
    for ev in t.range10[RANGE_DEFAULT[0]]:
        i = ev["i"]
        if not np.isfinite(t.close[i]) or not L4._avail(t, i, ev["d"]):
            continue
        out.append(dict(i=i, d=ev["d"], setup="RANGE", en87=False, levels=FX.range_levels(ev, *RANGE_DEFAULT[1:])))
    for e in out:
        i, d = e["i"], e["d"]
        x = t.ext10.get(i) if e["setup"] == "E03" else None
        S = t.S9[F9.skey(S9.REF_REP)][i]; q = t.q9["REF"]
        e["f"] = dict(er10=S9.er10(t, i), rank=(x or {}).get("rank_all"), elapsed=(t.minute[i] - 780) / 90., fric=FX.nominal_friction(t, i, d),
                      oiz=float(np.clip(d * S / q, -3, 3)) if np.isfinite(S) and np.isfinite(q) and q > 0 else math.nan,
                      er_rank=FX.er_rank(t, i), rvr=float(t.obs10[i, 2]))
        F = t.f[:, 3]; A = t.features[10][i, 4]
        e["dir8"] = float(d * (F[i + 8] - F[i]) / A) if i + 8 < t.n and np.isfinite([F[i + 8], F[i], A]).all() and A > 0 else math.nan
    return out


def applicable(e):
    return TREND if e["setup"] == "E03" else ("RANGE",)


def label_events(book, verbose=False):
    """Single-event lifecycles for every applicable action (ordinary and adverse). Returns {date index: [event]}."""
    base = lab10.R10(L7.E03_ENV, sig9=LBL)
    rules = {a: lab10.profiled(base, p) for a, p in PROF.items()}
    out = {}
    for k, t in enumerate(book):
        evs = events(t); out[k] = evs
        for e in evs:
            e["label"] = {}; e["date"] = k
            arr = np.zeros(t.n, np.int8); arr[e["i"]] = e["d"]
            t.meta9[LBL] = {e["i"]: dict(range10=e["levels"])} if e["setup"] == "RANGE" else {}
            for a in applicable(e):
                lab = {}
                for sc in ("ordinary", "adverse"):
                    d = lab10.run_day10(t, rules[a], sc, 30000., 2500., False, direct=arr)
                    lab[sc] = (d["net"], d["trades"])
                e["label"][a] = lab
        t.meta9.pop(LBL, None)
    return out


# ------------------------------------------------------------------ small learners
FEATS = {"WITH_OI": ("er10", "rank", "elapsed", "fric", "oiz"), "NO_OI": ("er10", "rank", "elapsed", "fric")}
ROUTE = ("er_rank", "rvr", "fric")
IMPUTE = {"rank": .5}


def matrix(rows, names, med=None):
    X = np.array([[r["f"][n] if r["f"][n] is not None else np.nan for n in names] for r in rows], float).reshape(len(rows), len(names))
    if med is None:
        med = np.array([IMPUTE.get(n, np.nan) if not np.isfinite(X[:, j]).any() else np.nanmedian(X[:, j]) for j, n in enumerate(names)])
        med = np.where(np.isfinite(med), med, 0.)
    for j, n in enumerate(names):
        bad = ~np.isfinite(X[:, j])
        X[bad, j] = IMPUTE.get(n, med[j])
    return X, med


def weights(dates):
    dates = np.asarray(dates); w = np.zeros(len(dates))
    for d in np.unique(dates):
        m = dates == d; w[m] = 1. / m.sum()
    return w


def ridge_fit(X, y, w, lam):
    mu = (w[:, None] * X).sum(0) / w.sum(); sd = np.sqrt((w[:, None] * (X - mu) ** 2).sum(0) / w.sum()); sd[sd <= 1e-12] = 1.
    Z = (X - mu) / sd; ym = (w * y).sum() / w.sum()
    A = Z.T @ (w[:, None] * Z) + lam * np.eye(Z.shape[1]); b = np.linalg.solve(A, Z.T @ (w * (y - ym)))
    return ("RIDGE", mu, sd, b, ym)


def stump_fit(X, y, w, dates, min_dates):
    ym = (w * y).sum() / w.sum(); best = None; base = float((w * (y - ym) ** 2).sum())
    dates = np.asarray(dates)
    for f in range(X.shape[1]):
        for th in np.unique(np.quantile(X[:, f], np.arange(.1, .91, .1))):
            L = X[:, f] <= th
            if len(np.unique(dates[L])) < min_dates or len(np.unique(dates[~L])) < min_dates:
                continue
            yl = (w[L] * y[L]).sum() / w[L].sum(); yr = (w[~L] * y[~L]).sum() / w[~L].sum()
            sse = float((w[L] * (y[L] - yl) ** 2).sum() + (w[~L] * (y[~L] - yr) ** 2).sum())
            if sse < base - 1e-12 and (best is None or sse < best[0] - 1e-12):
                best = (sse, f, float(th), yl, yr)
    if best is None:
        return ("CONST", ym)
    return ("STUMP", best[1], best[2], best[3], best[4])


def predict(m, X):
    if m[0] == "RIDGE":
        _, mu, sd, b, ym = m
        return ym + ((X - mu) / sd) @ b
    if m[0] == "STUMP":
        _, f, th, yl, yr = m
        return np.where(X[:, f] <= th, yl, yr)
    return np.full(len(X), m[1])


def fit_one(kind, reg, X, y, w, dates):
    if kind == "RIDGE" or kind == "DIRECTION":
        return ridge_fit(X, y, w, 1. if reg == "LIGHT" else 10.)
    if kind == "STUMP":
        return stump_fit(X, y, w, dates, 20 if reg == "LIGHT" else 40)
    return ("CONST", float((w * y).sum() / w.sum()))


def rewards(rows, a):
    net = np.array([r["label"][a]["adverse"][0] for r in rows])
    return net / 2500., np.maximum(0., -net) / 2500.


def funded_dates(rows, a):
    return len({r["date"] for r in rows if r["label"][a]["adverse"][1] > 0})


# ------------------------------------------------------------------ EN118
class Model118:
    def __init__(self, kind, reg, k, feats, train, ndates, seed):
        self.kind, self.reg, self.k, self.names = kind, reg, k, FEATS[feats]
        self.models = {}; self.boot = {}; self.supported = {}; self.med = {}
        self.enough = ndates >= 40
        rng = np.random.default_rng(seed)
        for a in TREND + ("RANGE",):
            rows = [r for r in train if a in r["label"]]
            self.supported[a] = bool(self.enough and rows and funded_dates(rows, a) >= 20)
            if not self.supported[a]:
                continue
            X, med = matrix(rows, self.names); self.med[a] = med
            dates = [r["date"] for r in rows]; w = weights(dates)
            if kind == "DIRECTION":
                if a != "LEGACY_100_8":
                    self.supported[a] = False; continue
                y = np.array([r["dir8"] for r in rows]); ok = np.isfinite(y)
                self.models[a] = (fit_one("DIRECTION", reg, X[ok], y[ok], weights(np.asarray(dates)[ok]), np.asarray(dates)[ok]),)
                continue
            r_, l_ = rewards(rows, a)
            self.models[a] = (fit_one(kind, reg, X, r_, w, dates), fit_one(kind, reg, X, l_, w, dates))
            if k > 0:
                ud = sorted(set(dates)); by = {d: [n for n, x in enumerate(dates) if x == d] for d in ud}; bs = []
                for _ in range(BOOT):
                    pick = rng.choice(len(ud), size=len(ud), replace=True)
                    idx = np.concatenate([by[ud[p]] for p in pick]); bd = np.repeat(np.arange(len(pick)), [len(by[ud[p]]) for p in pick])
                    wb = weights(bd)
                    bs.append((fit_one(kind, reg, X[idx], r_[idx], wb, bd), fit_one(kind, reg, X[idx], l_[idx], wb, bd)))
                self.boot[a] = bs
        self.id = hashlib.sha256(repr((kind, reg, k, feats, sorted(self.supported.items()), ndates, len(train))).encode()).hexdigest()[:12]

    def score(self, a, rows):
        X, _ = matrix(rows, self.names, self.med[a])
        if self.kind == "DIRECTION":
            return predict(self.models[a][0], X)
        mr, ml = self.models[a]; s = predict(mr, X) - .5 * predict(ml, X)
        if self.k > 0:
            B = np.array([predict(br, X) - .5 * predict(bl, X) for br, bl in self.boot[a]])
            s = s - self.k * B.std(0)
        return s

    def any_supported(self):
        return any(self.supported.values())


def policy118(model, evs):
    """Per-minute action choice. Returns {i: (action, d, levels)}; the fallback is EN87's action at EN87 minutes."""
    by = {}
    for e in evs:
        by.setdefault(e["i"], []).append(e)
    out = {}; log = []
    scores = {}
    for a in TREND + ("RANGE",):
        rows = [e for e in evs if a in applicable(e)]
        if rows and model.supported.get(a):
            for e, s in zip(rows, model.score(a, rows)):
                scores[(e["i"], e["setup"], a)] = float(s)
    for i in sorted(by):
        if not model.any_supported():
            e87 = next((e for e in by[i] if e["en87"]), None)
            if e87:
                out[i] = ("LEGACY_100_8", e87["d"], None); log.append((i, "FALLBACK_EN87"))
            else:
                log.append((i, "FALLBACK_CASH"))
            continue
        cand = []
        for e in by[i]:
            for n, a in enumerate(applicable(e)):
                key = (i, e["setup"], a)
                if key in scores:
                    cand.append((scores[key], -ACTIONS.index(a), a, e))
        cand = [c for c in cand if c[0] > 0]
        if not cand:
            log.append((i, "CASH")); continue
        cand.sort(key=lambda c: (c[0], c[1]), reverse=True)
        s, _, a, e = cand[0]
        out[i] = (a, e["d"], e.get("levels")); log.append((i, a))
    return out, log


def write_policy(t, key, choice, tag=""):
    arr = np.zeros(t.n, np.int8); meta = {}
    for i, (a, d, levels) in choice.items():
        arr[i] = d; m = dict(tag10=a + tag)
        if PROF[a]:
            m["prof10"] = PROF[a]
        if a == "RANGE":
            m["range10"] = levels
        meta[i] = m
    t.sig9[key] = arr; t.meta9[key] = meta


# ------------------------------------------------------------------ EN120 tree
def tree_value(rows, profs):
    w = weights([r["date"] for r in rows]); W = float(w.sum()); best = 0.; V = {}
    for p in profs:
        m = np.array([avail120(r, p) for r in rows], bool)
        if not m.any():
            continue
        r_, l_ = rewards([r for r, x in zip(rows, m) if x], PROFILES120[p])
        ww = w[m]; V[p] = float((ww * (r_ - .5 * l_)).sum() / ww.sum())
        best = max(best, V[p])
    return W * best, V


def avail120(r, p):
    return (PROFILES120[p] in r["label"]) and (r["en87"] if p in ("EN87", "EN111") else r["setup"] == "RANGE")


def fit_tree(rows, depth, profs, min_dates=20):
    X, med = matrix(rows, ROUTE)
    dates = np.array([r["date"] for r in rows])

    def grow(idx, dep):
        node_rows = [rows[n] for n in idx]; obj, V = tree_value(node_rows, profs)
        if dep == 0:
            return dict(leaf=True, idx=idx)
        best = None
        for f in range(X.shape[1]):
            for th in np.unique(np.quantile(X[idx, f], np.arange(.1, .91, .1))):
                L = idx[X[idx, f] <= th]; R_ = idx[X[idx, f] > th]
                if len(np.unique(dates[L])) < min_dates or len(np.unique(dates[R_])) < min_dates:
                    continue
                g = tree_value([rows[n] for n in L], profs)[0] + tree_value([rows[n] for n in R_], profs)[0] - obj
                if g > 1e-12 and (best is None or g > best[0] + 1e-12):
                    best = (g, f, float(th), L, R_)
        if best is None:
            return dict(leaf=True, idx=idx)
        return dict(leaf=False, f=best[1], th=best[2], L=grow(best[3], dep - 1), R=grow(best[4], dep - 1))
    return grow(np.arange(len(rows)), depth), med


class Model120:
    def __init__(self, depth, train, ndates, seed):
        rng = np.random.default_rng(seed)
        rows = [r for r in train if r["en87"] or r["setup"] == "RANGE"]
        self.supported = {p: bool(ndates >= 40 and funded_dates([r for r in rows if avail120(r, p)], PROFILES120[p]) >= 20)
                          if any(avail120(r, p) for r in rows) else False for p in PROFILES120}
        self.profs = [p for p in PROFILES120 if self.supported[p]]
        self.tree, self.med = (fit_tree(rows, depth, self.profs) if self.profs and rows else (dict(leaf=True, idx=np.arange(len(rows))), np.zeros(3)))
        self.rows = rows
        self.values = {}
        for leaf in self.leaves(self.tree):
            lr = [rows[n] for n in leaf["idx"]]; vals = {}
            for p in self.profs:
                sub = [r for r in lr if avail120(r, p)]
                if not sub:
                    continue
                ud = sorted({r["date"] for r in sub}); by = {d: [r for r in sub if r["date"] == d] for d in ud}
                v0 = self._v(sub, p); bs = []
                for _ in range(BOOT):
                    pick = rng.choice(len(ud), size=len(ud), replace=True)
                    rs = []; ds = []
                    for n, pp in enumerate(pick):
                        rs += by[ud[pp]]; ds += [n] * len(by[ud[pp]])
                    bs.append(self._v(rs, p, ds))
                vals[p] = v0 - float(np.std(bs))
            leaf["values"] = vals
        self.id = hashlib.sha256(repr((depth, ndates, len(rows), self.describe())).encode()).hexdigest()[:12]

    @staticmethod
    def _v(rows, p, dates=None):
        w = weights(dates if dates is not None else [r["date"] for r in rows]); r_, l_ = rewards(rows, PROFILES120[p])
        return float((w * (r_ - .5 * l_)).sum() / w.sum())

    def leaves(self, node):
        if node["leaf"]:
            return [node]
        return self.leaves(node["L"]) + self.leaves(node["R"])

    def leaf_of(self, x):
        node = self.tree
        while not node["leaf"]:
            node = node["L"] if x[node["f"]] <= node["th"] else node["R"]
        return node

    def value(self, p, e):
        X, _ = matrix([e], ROUTE, self.med)
        return self.leaf_of(X[0]).get("values", {}).get(p)

    def describe(self):
        def d(n):
            if n["leaf"]:
                return dict(values={k: round(v, 5) for k, v in n.get("values", {}).items()}, n=int(len(n["idx"])))
            return dict(f=ROUTE[n["f"]], th=round(n["th"], 5), L=d(n["L"]), R=d(n["R"]))
        return d(self.tree)


def policy120(model, evs, margin, state):
    """Controller decisions in time order; state = {"current": profile} persists across sessions (serialisable)."""
    by = {}
    for e in evs:
        by.setdefault(e["i"], []).append(e)
    out = {}; log = []
    for i in sorted(by):
        es = by[i]; e87 = next((e for e in es if e["en87"]), None); rng_ = next((e for e in es if e["setup"] == "RANGE"), None)
        av = {}
        if e87:
            av["EN87"] = e87; av["EN111"] = e87
        if rng_:
            av["EN117"] = rng_
        if not model.profs:
            if e87:
                out[i] = ("LEGACY_100_8", e87["d"], None); log.append((i, "FALLBACK_EN87"))
            continue
        vals = {p: model.value(p, e) for p, e in av.items() if p in model.profs}
        vals = {p: v for p, v in vals.items() if v is not None}
        if not vals:
            if e87:
                out[i] = ("LEGACY_100_8", e87["d"], None); log.append((i, "UNSUPPORTED_EN87"))
            continue
        top = sorted(vals.items(), key=lambda kv: kv[1], reverse=True)
        p, v = top[0]
        if len(top) > 1 and abs(top[0][1] - top[1][1]) <= 1e-12:
            p = "EN87" if "EN87" in av else None
            v = vals.get("EN87", 0.) if p else 0.
        cur = state.get("current")
        if p is not None and cur in vals and cur != p and vals[cur] > 0 and v - vals[cur] <= margin:
            p, v = cur, vals[cur]
        if p is None or v <= 0:
            log.append((i, "CASH")); continue
        e = av[p]; a = PROFILES120[p]
        out[i] = (a, e["d"], e.get("levels")); log.append((i, p)); state["current"] = p
    return out, log


def union_policy(evs):
    out = {}
    for e in sorted(evs, key=lambda e: (e["i"], e["setup"] != "E03")):
        if e["i"] in out:
            continue
        if e["en87"]:
            out[e["i"]] = ("NEARER_150_12", e["d"], None)
        elif e["setup"] == "RANGE":
            out[e["i"]] = ("RANGE", e["d"], e["levels"])
    return out
