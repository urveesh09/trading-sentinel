"""EN56-EN70 scorer: PLAN6.md's frozen rules applied mechanically, once.

    python en_score6.py selftest   the whole pipeline on truncated books, two null seeds and a short bootstrap;
                                   nothing written, no rupees printed
    python en_score6.py freeze     hashes this round's files, every transitive lab / loader / fee module, the data
                                   bindings, the recorder export's manifests and the Breeze rows EN70 reads -> freeze6.json
    python en_score6.py score      refuses unless the freeze is committed and unchanged; start receipt; results6.json +
                                   anatomy6.json, once"""
from __future__ import annotations
import hashlib, json, math, random, subprocess, sys, time
from collections import defaultdict
from dataclasses import replace, asdict
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import en_lab6 as L6  # noqa: E402
import en_ml6 as ML  # noqa: E402
import pk6 as PK  # noqa: E402

L5, L4, L3, E = L6.L5, L6.L4, L6.L3, L6.E
SIM = HERE.parent; EN = SIM / "2026-11-17-expiry-en"; EN41 = SIM / "2026-11-18-expiry-en41"; REPO = HERE.parents[3]
LOCAL_FILES = ("PLAN6.md", "en_lab6.py", "en_ml6.py", "pk6.py", "en_score6.py")
EXTERNAL = {**{f: EN / f for f in ("en_lab4.py", "en4_data.py", "en_lab3.py", "en_lab2.py", "en_lab.py", "en_base.py", "exam2023.py",
                                    "exam2023b.py", "data-binding4.json")},
            "en_lab5.py": EN41 / "en_lab5.py", "tr01.py": EN41 / "tr01.py",
            "r8b_lab.py": SIM / "2026-11-03-expiry-round8/r8b_lab.py", "e031_lab.py": SIM / "2026-11-03-expiry-e031/lab.py",
            "e03_lab.py": SIM / "2026-11-03-expiry-e03/e03_lab.py", "e02_lab.py": SIM / "2026-11-03-expiry-e02/e02_lab.py",
            "data.py": SIM / "2026-11-03-expiry-e02/data.py", "expiry_paper.py": REPO / "python-engine/expiry_paper.py",
            "cost_schedules.py": REPO / "python-engine/cost_schedules.py", "data-binding.json": SIM / "2026-11-02-expiry-e02/data-binding.json"}
RESULTS, ANAT, START, FREEZE = HERE / "results6.json", HERE / "anatomy6.json", HERE / "results6-started.json", HERE / "freeze6.json"
SC = ("ordinary", "adverse", "catastrophe")
SEED = 20261118
ALPHA = ("EN60", "EN61", "EN62", "EN64")
MODS = {"EN58": "EN55", "EN59": "EN59_en52_ctl", "EN63": "EN63_native8_ctl", "EN65": "EN65_bank_ctl", "EN67": "EN55"}
FAMILY = ("EN58", "EN59", "EN60", "EN61", "EN62", "EN63", "EN64", "EN65", "EN67")
FULL = ["E032_30k", "EN55", "E032_sym", "E032_env", "EN60", "EN60_orb5_ctl", "EN60_1250_diag", "EN62", "EN62_dir_ctl", "EN62_decay_ctl",
        "EN62_1250_diag", "EN64", "EN64_ret_ctl", "EN64_vol_ctl", "EN64_1250_diag", "EN63", "EN63_native8_ctl", "EN63_native15", "EN63_liq8",
        "EN63_cash_diag", "EN65", "EN65_bank_ctl", "EN65_en12_diag", "EN59", "EN59_en52_ctl", "EN59_en52_5000", "EN59_closeb_diag",
        "EN59_en51_2500", "EN67", *[k for k in L6.ARMS if k.startswith("EN67_e")], *[k for k in L6.ARMS if k.startswith("EN57_")]]
ML_ARMS = list(ML.ARMS)
NULLS = {"EN60": "EN60", "EN62": "EN62", "EN64": "EN64"}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git(*a):
    return subprocess.run(("git",) + a, cwd=HERE, capture_output=True, text=True).stdout.strip()


def _paths():
    return {**{f: HERE / f for f in LOCAL_FILES}, **EXTERNAL}


def _data_bindings():
    import sklearn
    b = PK.breeze_options()
    canon = json.dumps(sorted([[k[0], k[1], k[2], *v] for k, v in b.items()]), separators=(",", ":"))
    return dict(tr01=PK.tr01.verify(), breeze_nov17_options_sha256=hashlib.sha256(canon.encode()).hexdigest(), breeze_nov17_option_rows=len(b),
                exam2026_sqlite_sha256=sha(EN / "_local/exam2026.sqlite"), sklearn=sklearn.__version__, numpy=np.__version__)


def freeze():
    assert not RESULTS.exists() and not START.exists()
    FREEZE.write_text(json.dumps(dict(files={k: sha(p) for k, p in _paths().items()}, data=_data_bindings(), head=git("rev-parse", "HEAD")),
                                 indent=2) + "\n")
    print("FROZEN", git("rev-parse", "HEAD"))


# ---------------------------------------------------------------- measurement
def window(m):
    return "12:30-13:30" if m < 810 else "13:30-14:30" if m < 870 else "14:30-15:00" if m < 900 else "15:00+"


def tickets(days, by):
    out = []
    for d in days:
        t = by[(d.get("und") or "NIFTY", d["day"])] if (d.get("und") or "NIFTY", d["day"]) in by else None
        for p in d["positions"]:
            sells = [e for e in p["events"] if e.get("side") == "SELL"]
            m = int(t.minute[p["decision_i"]]) if t is not None else -1
            out.append(dict(day=p["day"], key=f'{p["day"]}|{int(p["decision_i"])}|{int(p["direction"])}|{p.get("origin")}',
                            side="S" if p["direction"] == 0 else "P" if p["direction"] < 0 else "C", minute=m, lots=p["lots"],
                            net=round(p["net"], 2), fees=round(p["fees"], 2), origin=p.get("origin"),
                            first_exit=sells[0].get("reason", "") if sells else ("UNRESOLVED" if p.get("unresolved") else ""),
                            unresolved=bool(p.get("unresolved"))))
    return out


def metrics(days):
    v = [d["net"] for d in days]; top = sorted(v, reverse=True) + [0., 0.]
    yrs = defaultdict(float)
    for d in days:
        yrs[d["day"][:4]] += d["net"]
    return dict(net=round(sum(v), 2), without_best=round(sum(v) - max(top[0], 0.), 2), without_top2=round(sum(v) - max(top[0], 0.) - max(top[1], 0.), 2),
                worst=round(min(v, default=0.), 2), tickets=int(sum(d["trades"] for d in days)), expiries=int(sum(d["trades"] > 0 for d in days)),
                sessions=len(days), per_expiry=round(sum(v) / max(1, len(v)), 2), fees=round(sum(d["fees"] for d in days), 2),
                unresolved=int(sum(d["unresolved"] for d in days)), by_year={k: round(x, 2) for k, x in sorted(yrs.items())},
                worst_marked=round(min([d.get("marked_worst", 0.) for d in days], default=0.), 2))


def tmetrics(tk):
    g = lambda f: {k: dict(tickets=len(v), winners=sum(x["net"] > 0 for x in v), net=round(sum(x["net"] for x in v), 2))
                   for k, v in sorted(_group(tk, f).items())}
    return dict(by_side=g(lambda x: x["side"]), by_first_exit=g(lambda x: x["first_exit"]), by_window=g(lambda x: window(x["minute"])),
                by_origin=g(lambda x: x["origin"] or ""), winners=sum(x["net"] > 0 for x in tk))


def _group(xs, f):
    out = defaultdict(list)
    for x in xs:
        out[f(x)].append(x)
    return out


def wallet_view(w):
    return dict(P=w["P"], swept=w["swept"], wallet=w["wallet"], halted=w["halted"], first_halt=w["first_halt"], liq_dd=w["liq_dd"], close_dd=w["close_dd"])


def run_arm(name, arm, book, by, keep_days=False):
    out = {}; days_ord = None
    for sc in SC:
        r = L6.run_fixed6(book, arm, sc, details=(sc == "ordinary"))
        for d in r["days"]:
            d["und"] = L6.und(by_day(by, d["day"], book))
        out[sc] = metrics(r["days"])
        if sc == "ordinary":
            days_ord = r["days"]; out["tickets"] = tmetrics(tickets(r["days"], by))
    for sc in ("ordinary", "adverse"):
        out[f"wallet|{sc}"] = wallet_view(L6.run_wallet6(book, arm, sc))
    return out, days_ord


def by_day(by, day, book):
    u = L6.und(book[0]) if book else "NIFTY"
    return by[(u, day)]


def daymap(B):
    return {(L6.und(t), t.day): t for book in B.values() for t in book}


def affected(da, db):
    """Parents whose ledger differs between two arms (same decision bar and side), or exist in only one."""
    n = 0; exp = 0
    for x, y in zip(da, db):
        ka = {(p["decision_i"], p["direction"], p.get("origin")): (round(p["net"], 2), p["lots"]) for p in x["positions"]}
        kb = {(p["decision_i"], p["direction"], p.get("origin")): (round(p["net"], 2), p["lots"]) for p in y["positions"]}
        diff = {k for k in set(ka) | set(kb) if ka.get(k) != kb.get(k)}
        n += len(diff); exp += bool(diff)
    return n, exp


def boot_p(x, seed, B=20000):
    x = np.asarray(x, float); n = len(x)
    if n == 0:
        return 1.
    rng = np.random.default_rng(seed); m = np.empty(B)
    for s in range(0, B, 2000):
        k = min(2000, B - s); m[s:s + k] = x[rng.integers(0, n, (k, n))].mean(1)
    return float((1 + np.sum(m <= 0)) / (B + 1))


def _seed(slot, bk):
    """Deterministic bootstrap seed per hypothesis (never Python's per-process hash())."""
    return SEED + 10 * FAMILY.index(slot) + (0 if bk == "NIFTY" else 1)


def holm(ps):
    keys = sorted(ps, key=lambda k: ps[k]); m = len(keys); adj = {}; run = 0.
    for r, k in enumerate(keys):
        run = max(run, min(1., (m - r) * ps[k])); adj[k] = round(run, 4)
    return adj


# ---------------------------------------------------------------- the round
def pipeline(B, seeds, head, quiet=False, boot=20000, paths=2000):
    t0 = time.time(); log = (lambda *a: None) if quiet else (lambda *a: print(f"[{time.time() - t0:6.0f}s]", *a, flush=True))
    L5.install(); by = daymap(B)
    for book in B.values():
        L6.prepare62(book)
    mllog = ML.prepare(B); log("prepared EN62 thresholds and EN61 walk-forward")
    res = dict(freeze_head=head, sessions={k: len(v) for k, v in B.items()}, arms={}, status={}, tests={}, nulls={}, diagnostics={})
    anat = dict(days={}, tickets={})
    DAYS = {}
    for name in FULL + ML_ARMS:
        arm = L6.ARMS.get(name) or ML.ARMS[name]
        for bk, book in B.items():
            out, days = run_arm(name, arm, book, by)
            res["arms"].setdefault(name, {})[bk] = out; DAYS[(name, bk)] = days
            anat["days"].setdefault(name, {})[bk] = [(d["day"], d["net"], d["trades"]) for d in days]
            anat["tickets"].setdefault(name, {})[bk] = tickets(days, by)
        log("arm", name)
    # evaluation subsets: EN61 from its first scored session, EN62 from its first thresholded session (controls matched)
    sub = {}
    for bk, book in B.items():
        first61 = next((k for k, r in enumerate(mllog[bk]) if not r.get("abstain")), len(book))
        first62 = next((k for k, t in enumerate(book) if L6.RES62[(L6.und(t), t.day)]["thresholds"]), len(book))
        sub[("EN61", bk)] = first61; sub[("EN62", bk)] = first62
    res["evaluation_from"] = {f"{k[0]}|{k[1]}": B[k[1]][v].day if v < len(B[k[1]]) else None for k, v in sub.items()}

    def view(name, bk, slot):
        """Metrics of an arm on a slot's evaluation sessions (ordinary + adverse fixed-cap, wallet ordinary)."""
        k = sub.get((slot, bk), 0); book = B[bk][k:]; arm = L6.ARMS.get(name) or ML.ARMS[name]
        if k == 0:
            r = res["arms"][name][bk]; return dict(ordinary=r["ordinary"], adverse=r["adverse"], wallet=r["wallet|ordinary"], days=DAYS[(name, bk)])
        o = L6.run_fixed6(book, arm, "ordinary", details=True); a = L6.run_fixed6(book, arm, "adverse")
        return dict(ordinary=metrics(o["days"]), adverse=metrics(a["days"]), wallet=wallet_view(L6.run_wallet6(book, arm)), days=o["days"])
    # nulls
    for slot, name in NULLS.items():
        for bk, book in B.items():
            k = sub.get((slot, bk), 0); nets = []
            for s in range(seeds):
                L3.NULL = f"{slot}-{s}"
                nets.append(L6.run_fixed6(book[k:], L6.ARMS[name])["summary"]["net"])
            L3.NULL = None
            res["nulls"].setdefault(slot, {})[bk] = dict(median=round(float(np.median(nets)), 2), p10=round(float(np.percentile(nets, 10)), 2),
                                                        p90=round(float(np.percentile(nets, 90)), 2), seeds=seeds)
    log("nulls")
    # verdicts and the family test
    ps = {}; detail = {}
    for slot in FAMILY:
        for bk, book in B.items():
            if slot == "EN58":
                ps[f"{slot}|{bk}"] = 1.; detail[(slot, bk)] = dict(support=False, why="one packet session (NIFTY Nov 17) by construction")
                continue
            if slot in ALPHA:
                a, c = view(slot, bk, slot), view("E032_env", bk, slot if slot in ("EN61", "EN62") else "")
                sup = a["ordinary"]["tickets"] >= 30 and a["ordinary"]["expiries"] >= 20
                x = [d["net"] for d in a["days"]]
                ps[f"{slot}|{bk}"] = boot_p(x, _seed(slot, bk), boot) if sup else 1.
                detail[(slot, bk)] = dict(support=sup, arm=a, ctl=c)
            else:
                ctl = MODS[slot]; a, c = view(slot, bk, ""), view(ctl, bk, "")
                n_aff, e_aff = affected(c["days"], a["days"])
                sup = n_aff >= 20 and e_aff >= 10
                x = [p["net"] - q["net"] for p, q in zip(a["days"], c["days"])]
                ps[f"{slot}|{bk}"] = boot_p(x, _seed(slot, bk), boot) if sup else 1.
                detail[(slot, bk)] = dict(support=sup, arm=a, ctl=c, affected=n_aff, affected_expiries=e_aff)
    adj = holm(ps)
    for (slot, bk), dt in detail.items():
        p = adj[f"{slot}|{bk}"]
        res["tests"][f"{slot}|{bk}"] = dict(p=round(ps[f"{slot}|{bk}"], 4), holm=p, support=dt["support"],
                                           **({k: dt[k] for k in ("affected", "affected_expiries") if k in dt}))
        if slot == "EN58":
            v = "INCONCLUSIVE"
        elif not dt["support"]:
            v = "INCONCLUSIVE"
        elif slot in ALPHA:
            a, c = dt["arm"], dt["ctl"]
            ok = (a["ordinary"]["net"] > 0 and a["adverse"]["net"] > 0 and a["ordinary"]["without_top2"] > 0 and
                  a["ordinary"]["net"] > c["ordinary"]["net"] and a["adverse"]["net"] > c["adverse"]["net"] and
                  a["ordinary"]["worst"] >= c["ordinary"]["worst"] and p < .10)
            v = "DEVELOPMENT CANDIDATE (FORWARD-ONLY)" if ok else "FAIL"
        else:
            a, c = dt["arm"], dt["ctl"]
            halt_ok = a["wallet"]["first_halt"] is None or (c["wallet"]["first_halt"] is not None and a["wallet"]["first_halt"] >= c["wallet"]["first_halt"])
            imp = (a["ordinary"]["net"] >= c["ordinary"]["net"] and a["adverse"]["net"] >= c["adverse"]["net"] and a["ordinary"]["net"] > 0 and
                   a["ordinary"]["worst"] >= c["ordinary"]["worst"] and halt_ok and p < .10)
            if slot == "EN67":
                imp = imp and a["ordinary"]["tickets"] >= 1.25 * c["ordinary"]["tickets"]
            n = a["ordinary"]["sessions"]
            prot = (a["ordinary"]["net"] >= c["ordinary"]["net"] - 25 * n and a["adverse"]["net"] >= c["adverse"]["net"] - 25 * n and
                    (a["ordinary"]["worst"] > c["ordinary"]["worst"] or a["wallet"]["liq_dd"] < c["wallet"]["liq_dd"]))
            v = "IMPROVEMENT CANDIDATE (FORWARD-ONLY)" if imp else "PROTECTION ONLY" if prot else "FAIL"
        res["status"].setdefault(slot, {})[bk] = v
        if slot != "EN58":
            res["tests"][f"{slot}|{bk}"]["view"] = dict(arm={kk: dt["arm"][kk] for kk in ("ordinary", "adverse", "wallet")},
                                                        ctl={kk: dt["ctl"][kk] for kk in ("ordinary", "adverse", "wallet")})
    log("verdicts")
    res["ml61"] = ml_summary(mllog)
    res["diagnostics"]["EN56"] = en56(B, by); log("EN56")
    res["diagnostics"]["EN57"] = en57(B, by, DAYS); log("EN57")
    res["diagnostics"]["EN66"] = en66(B); log("EN66")
    res["diagnostics"]["EN68"] = en68(B, paths); log("EN68")
    res["diagnostics"]["EN69"] = en69(B, by, DAYS); log("EN69")
    pk = packets(); res["diagnostics"].update(pk); log("packets")
    res["status"]["EN56"] = {"ALL": "ANSWERED"}; res["status"]["EN57"] = {"ALL": "ANSWERED"}; res["status"]["EN66"] = {"ALL": "ANSWERED"}
    res["status"]["EN68"] = {"ALL": "ANSWERED"}; res["status"]["EN69"] = {"ALL": "ANSWERED"}
    res["status"]["EN70"] = {"NIFTY": pk["EN70"]["verdict"]}
    return res, anat


def ml_summary(mllog):
    out = {}
    for bk, log in mllog.items():
        sc = [r for r in log if not r.get("abstain")]
        out[bk] = dict(sessions=len(log), scored_sessions=len(sc), hgb_abstained=sum(1 for r in sc if r.get("abstain_hgb")),
                       abstain_reasons=dict(sorted(_count(r.get("abstain_hgb", "") for r in sc if r.get("abstain_hgb")).items())),
                       max_expected=round(max([r.get("max_E_hgb", -9) for r in sc], default=-9), 4),
                       logloss_model=_mean([r.get("calib_logloss_model") for r in sc]), logloss_icpt=_mean([r.get("calib_logloss_icpt") for r in sc]),
                       temperature_median=_mean([r.get("T") for r in sc], med=True))
    rows = L6.DIAG61
    for bk in mllog:
        r = [x for x in rows if x[0] == bk]
        if len(r) >= 50:
            E_ = np.array([x[2] for x in r]); y = np.array([x[3] for x in r]); q = np.quantile(E_, [.1, .9])
            out[bk]["top_decile_label"] = round(float(y[E_ >= q[1]].mean()), 4); out[bk]["bottom_decile_label"] = round(float(y[E_ <= q[0]].mean()), 4)
            out[bk]["mean_label"] = round(float(y.mean()), 4); out[bk]["positive_forecasts"] = int(np.sum(E_ > 0))
            out[bk]["class_shares"] = {k: round(float(np.mean([x[4] == k for x in r])), 4) for k in ML.CLASSES}
    return out


def _count(xs):
    c = defaultdict(int)
    for x in xs:
        c[x] += 1
    return c


def _mean(xs, med=False):
    xs = [x for x in xs if x is not None]
    return None if not xs else round(float(np.median(xs) if med else np.mean(xs)), 4)


# ---------------------------------------------------------------- EN56
def en56(B, by):
    F = {f: k for k, f in enumerate(L6.LIBF)}; out = {}
    for bk, book in B.items():
        rows = []; best = {R_: [] for R_ in L6.RES}; e03 = []; rnd = []
        for t in book:
            rs = L6.library(t); rows += rs
            for R_ in L6.RES:
                f = [r[F["net"]] for r in rs if r[F["R"]] == R_ and r[F["status"]] == 0]
                bi = int(np.argmax(f)) if f else -1
                fr = [r for r in rs if r[F["R"]] == R_ and r[F["status"]] == 0]
                best[R_].append((t.day, max(f) if f else 0., (fr[bi][F["mae"]] <= -.35 * fr[bi][F["buy"]]) if f else False))
            sig = L4.signals(t, L6.E032)[0]
            dec = [(int(i), int(sig[i])) for i in np.flatnonzero(sig) if 780 <= t.minute[i] <= 870]
            e03 += L6.library(t, decisions=dec)
            rng = random.Random(f"EN56-{t.day}")
            rnd += L6.library(t, decisions=[(i, rng.choice((1, -1))) for i, _ in dec])
        A = np.array([r[:22] for r in rows], float)
        adv = np.array([r[:22] for t in book for r in L6.library(t, "adverse")], float)
        out[bk] = dict(rows=len(rows), cells=_cells(A, F), cells_adverse=_cells(adv, F), buckets=_buckets(A, F),
                       e03_minutes=_cmp(np.array([r[:22] for r in e03], float), np.array([r[:22] for r in rnd], float), A, F),
                       ceiling={str(int(R_)): dict(expiries=len(v), best_ge_250=sum(x[1] >= 250 for x in v), best_ge_1250=sum(x[1] >= 1250 for x in v),
                                                   best_hit_stop_first=sum(1 for x in v if x[1] >= 250 and x[2]),
                                                   median_best=round(float(np.median([x[1] for x in v])), 2)) for R_, v in best.items()},
                       underlying=_und(A, F))
    out["packets"] = None                      # filled by packets()
    return out


def _cells(A, F):
    out = {}
    for R_ in L6.RES:
        for h in L6.HOR:
            for off in L6.OFFS:
                m = (A[:, F["R"]] == R_) & (A[:, F["h"]] == h) & (A[:, F["off"]] == off)
                if not m.any():
                    continue
                X = A[m]; fl = X[:, F["status"]] == 0; Y = X[fl]
                out[f"{int(R_)}|{h}|{off}"] = dict(decisions=int(m.sum()), filled=int(fl.sum()), unaffordable=int(np.sum(X[:, F["status"]] == 2)),
                                                   missing=int(np.sum(X[:, F["status"]] == 3)), nofill=int(np.sum(X[:, F["status"]] == 1)),
                                                   net_per_decision=round(float(X[:, F["net"]].mean()), 2),
                                                   net_per_fill=round(float(Y[:, F["net"]].mean()), 2) if len(Y) else None,
                                                   share_positive=round(float(np.mean(Y[:, F["net"]] > 0)), 4) if len(Y) else None,
                                                   gross_per_fill=round(float(Y[:, F["gross"]].mean()), 2) if len(Y) else None,
                                                   fees_per_fill=round(float(Y[:, F["fees"]].mean()), 2) if len(Y) else None,
                                                   slip_per_fill=round(float((Y[:, F["slip_in"]] + Y[:, F["slip_out"]]).mean()), 2) if len(Y) else None,
                                                   nospread_per_fill=round(float(Y[:, F["net_nospread"]].mean()), 2) if len(Y) else None,
                                                   mae=round(float(Y[:, F["mae"]].mean()), 2) if len(Y) else None,
                                                   mfe=round(float(Y[:, F["mfe"]].mean()), 2) if len(Y) else None,
                                                   ever_positive=round(float(np.mean(Y[:, F["t_pos"]] >= 0)), 4) if len(Y) else None,
                                                   unresolved=int(Y[:, F["unresolved"]].sum()) if len(Y) else 0, censored=int(Y[:, F["censored"]].sum()) if len(Y) else 0)
    return out


def _buckets(A, F):
    out = {}
    for b, lo, hi in (("12:30-13:00", 750, 780), ("13:00-13:30", 780, 810), ("13:30-14:00", 810, 840), ("14:00-14:30", 840, 871)):
        for h in L6.HOR:
            m = (A[:, F["R"]] == 2500.) & (A[:, F["h"]] == h) & (A[:, F["status"]] == 0) & (A[:, F["m"]] >= lo) & (A[:, F["m"]] < hi)
            if m.any():
                X = A[m]; out[f"{b}|{h}"] = dict(fills=int(m.sum()), net_per_fill=round(float(X[:, F["net"]].mean()), 2),
                                                 share_positive=round(float(np.mean(X[:, F["net"]] > 0)), 4),
                                                 calls=round(float(X[X[:, F["d"]] > 0, F["net"]].mean()), 2) if (X[:, F["d"]] > 0).any() else None,
                                                 puts=round(float(X[X[:, F["d"]] < 0, F["net"]].mean()), 2) if (X[:, F["d"]] < 0).any() else None)
    return out


def _cmp(Ae, Ar, A, F):
    out = {}
    for h in L6.HOR:
        for R_ in L6.RES:
            def mean_of(X, extra=None):
                m = (X[:, F["R"]] == R_) & (X[:, F["h"]] == h) & (X[:, F["status"]] == 0) & (X[:, F["m"]] >= 780) & (X[:, F["m"]] <= 870)
                return (round(float(X[m, F["net"]].mean()), 2), int(m.sum())) if m.any() else (None, 0)
            out[f"{int(R_)}|{h}"] = dict(e03=mean_of(Ae), random_side=mean_of(Ar), grid=mean_of(A))
    return out


def _und(A, F):
    m = (A[:, F["status"]] == 0) & (A[:, F["R"]] == 2500.) & (A[:, F["h"]] == 8) & np.isfinite(A[:, F["dF_atr"]])
    X = A[m]; right = X[:, F["dF_atr"]] > 0
    ok = np.isfinite(X[:, F["delta_rs"]])
    return dict(rows=int(m.sum()), direction_right=round(float(right.mean()), 4) if len(X) else None,
                right_but_option_lost=round(float(np.mean(X[right, F["net"]] <= 0)), 4) if right.any() else None,
                wrong_but_option_won=round(float(np.mean(X[~right, F["net"]] > 0)), 4) if (~right).any() else None,
                delta_equiv_mean=round(float(X[ok, F["delta_rs"]].mean()), 2) if ok.any() else None,
                option_net_mean=round(float(X[:, F["net"]].mean()), 2) if len(X) else None,
                corr_delta_vs_net=round(float(np.corrcoef(X[ok, F["delta_rs"]], X[ok, F["net"]])[0, 1]), 4) if ok.sum() > 2 else None)


# ---------------------------------------------------------------- EN57
def en57(B, by, DAYS):
    out = {}
    fac = [k for k in L6.ARMS if k.startswith("EN57_")]
    for bk, book in B.items():
        o = {}
        net = {k: DAYS[(k, bk)] for k in fac}
        tot = {k: sum(d["net"] for d in v) for k, v in net.items()}
        for f, pos in (("patient", 6), ("scout", 8), ("stall", 10)):
            pairs = [(k, k[:pos] + "1" + k[pos + 1:]) for k in fac if k[pos] == "0"]
            o[f"main_effect_{f}"] = round(float(np.mean([tot[b] - tot[a] for a, b in pairs])), 2)
        base = DAYS[("E032_30k", bk)]
        o["attribution"] = {k: attribution(base, DAYS[(k, bk)]) for k in fac + ["EN55"] if k != "EN57_p0s0r0"}
        pert = {}
        for name in ("E032_30k", "EN55"):
            arm = L6.ARMS[name]
            for tag, kw in (("ticks1", dict(ticks=1)), ("ticks2", dict(ticks=2)), ("delay1", dict(delay=1)),
                            ("passive_adversarial", dict(passive="adversarial")), ("passive_none", dict(passive="none"))):
                with L6.perturb(**kw):
                    f = L6.run_fixed6(book, arm)["summary"]; w = L6.run_wallet6(book, arm)
                pert[f"{name}|{tag}"] = dict(fixed=f["net"], worst=f["worst"], **wallet_view(w))
            base_w = L6.run_wallet6(book, arm); pert[f"{name}|base"] = dict(fixed=sum(d["net"] for d in DAYS[(name, bk)]), **wallet_view(base_w))
            qs = sorted({(t.day[:4], (int(t.day[5:7]) - 1) // 3) for t in book})
            for y, q in qs:
                k0 = next(k for k, t in enumerate(book) if (t.day[:4], (int(t.day[5:7]) - 1) // 3) == (y, q))
                w = L6.run_wallet6(book[k0:], arm); pert[f"{name}|from_{y}Q{q + 1}"] = wallet_view(w)
        o["perturbations"] = pert
        o["halt_crossings"] = {name: sum(1 for k, v in pert.items() if k.startswith(name + "|") and "from_" not in k and k != f"{name}|base"
                                         and (v["halted"] > 0) != (pert[f"{name}|base"]["halted"] > 0)) for name in ("E032_30k", "EN55")}
        if bk == "NIFTY":
            top = sorted(base, key=lambda d: -d["net"])[:2]; heroes = [d["day"] for d in top]; hv = {}
            for name in ("E032_30k", "EN55"):
                for tag, drop in (("drop_first", {heroes[0]}), ("drop_second", {heroes[1]}), ("drop_both", set(heroes))):
                    bb = [t for t in book if t.day not in drop]
                    hv[f"{name}|{tag}"] = dict(fixed=L6.run_fixed6(bb, L6.ARMS[name])["summary"]["net"], **wallet_view(L6.run_wallet6(bb, L6.ARMS[name])))
            o["heroes"] = dict(days=heroes, runs=hv)
        o["wallet_adverse_minus_ordinary"] = {k: round(DAYS_W(k, bk, book, "adverse") - DAYS_W(k, bk, book, "ordinary"), 2) for k in fac}
        out[bk] = o
    return out


def DAYS_W(name, bk, book, sc):
    return L6.run_wallet6(book, L6.ARMS[name], sc)["P"]


def attribution(base_days, arm_days):
    """Matched parents (same decision bar and side) vs new and lost ones; size / price-and-exit / fee split on matched."""
    m = dict(matched=0, matched_delta=0., size=0., exit_price=0., fees=0., new=0, new_net=0., lost=0, lost_net=0.)
    for x, y in zip(base_days, arm_days):
        ka = {(p["decision_i"], p["direction"]): p for p in x["positions"]}; kb = {(p["decision_i"], p["direction"]): p for p in y["positions"]}
        for k in set(ka) | set(kb):
            a, b = ka.get(k), kb.get(k)
            if a and b:
                ga, gb = a["net"] + a["fees"], b["net"] + b["fees"]
                size = (b["lots"] - a["lots"]) * (ga / a["lots"]) if a["lots"] else 0.
                m["matched"] += 1; m["matched_delta"] += b["net"] - a["net"]; m["size"] += size; m["exit_price"] += (gb - ga) - size
                m["fees"] -= b["fees"] - a["fees"]
            elif b:
                m["new"] += 1; m["new_net"] += b["net"]
            else:
                m["lost"] += 1; m["lost_net"] += a["net"]
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in m.items()}


# ---------------------------------------------------------------- EN66 / EN68
EN66_ARMS = ("E032_30k", "EN55", "E032_sym", "EN67")


def en66(B):
    C = L6.combined(B); lo, hi = C[0].day, C[-1].day; out = dict(period=[lo, hi], sessions=len(C))
    nif = [t for t in B["NIFTY"] if lo <= t.day <= hi]; weeks = max(1, len({_wk(t.day) for t in C}))
    for name in EN66_ARMS:
        arm = L6.ARMS[name]; o = {}
        for sc in ("ordinary", "adverse"):
            w = L6.run_wallet6(C, arm, sc); wn = L6.run_wallet6(nif, arm, sc); ws = L6.run_wallet6(B["SENSEX"], arm, sc)
            o[sc] = dict(combined=wallet_view(w), separate=dict(P=round(wn["P"] + ws["P"], 2), swept=round(wn["swept"] + ws["swept"], 2),
                                                                nifty=wallet_view(wn), sensex=wallet_view(ws)),
                         parents_per_week=round(w["summary"]["trades"] / weeks, 3), losing_weeks=_weeks(w["days"]))
        out[name] = o
    return out


def _wk(day):
    import datetime as dt
    y, w, _ = dt.date.fromisoformat(day).isocalendar(); return f"{y}-{w:02d}"


def _weeks(days):
    wk = defaultdict(float)
    for d in days:
        wk[_wk(d["day"])] += d["net"]
    v = list(wk.values()); return dict(weeks=len(v), losing=sum(x < 0 for x in v), flat=sum(x == 0 for x in v), winning=sum(x > 0 for x in v))


def en68(B, paths):
    out = {}; rng = np.random.default_rng(SEED)
    sets = {**B, "COMBINED": L6.combined(B)}
    for name in EN66_ARMS:
        arm = L6.ARMS[name]; full = L6.budget_of(arm); o = {}
        for bk, book in sets.items():
            pre = {}
            for t in book:
                for s in (1., .5, .25):
                    r = L6.day6(t, arm, "ordinary", 30000., full * s, False); pre[(L6.und(t), t.day, s)] = (r["net"], r.get("marked_worst", 0.))
                pre[(L6.und(t), t.day, 0.)] = (0., 0.)
            L = 104 if bk == "COMBINED" else 52; blk = 8 if bk == "COMBINED" else 4; n = len(book)
            ends, halts, sweeps, liq = [], 0, [], []
            for _ in range(paths):
                idx = []
                while len(idx) < L:
                    s0 = int(rng.integers(0, n)); idx += [(s0 + k) % n for k in range(blk)]
                idx = idx[:L]; P = W = peak = 0.; halted = False; lq = 0.
                for k in idx:
                    t = book[k]; dd = peak - P; sc = 0. if dd >= 4000 else .25 if dd >= 3000 else .5 if dd >= 1500 else 1.
                    assert 30000. + P - W >= full
                    halted |= sc == 0.; net, mw = pre[(L6.und(t), t.day, sc)]
                    lq = max(lq, peak - (P + min(0., mw)))
                    P += net; peak = max(peak, P); W += max(0., .5 * max(P, 0.) - W)
                ends.append(P); halts += halted; sweeps.append(W); liq.append(lq)
            e = np.array(ends)
            o[bk] = dict(paths=paths, length=L, block=blk, p_halt=round(halts / paths, 4), p_loss=round(float(np.mean(e < 0)), 4),
                         median=round(float(np.median(e)), 2), p5=round(float(np.percentile(e, 5)), 2), p95=round(float(np.percentile(e, 95)), 2),
                         mean_swept=round(float(np.mean(sweeps)), 2), liq_dd_median=round(float(np.median(liq)), 2), liq_dd_p95=round(float(np.percentile(liq, 95)), 2))
        out[name] = o
    return out


# ---------------------------------------------------------------- EN69
def en69(B, by, DAYS):
    out = {}
    for bk, book in B.items():
        tm = {t.day: t for t in book}; o = {}
        for name in ("E032_30k", "EN55"):
            agg = defaultdict(lambda: defaultdict(float)); cnt = defaultdict(int)
            for d in DAYS[(name, bk)]:
                t = tm[d["day"]]
                for p in d["positions"]:
                    side = "P" if p["direction"] < 0 else "C"; units_net = p["net"] + p["fees"]; marks = 0.; ok = True; parts = defaultdict(float)
                    for e in p["events"]:
                        if e["side"] != "SELL":
                            continue
                        x = L6.decompose(t, p["j"], p["decision_i"], e["decision_i"])
                        u = e["lots"] * L4.spec_of(t).lot
                        if x is None:
                            ok = False; break
                        marks += x["mark"] * u
                        if x["ok"]:
                            for k in ("underlying", "time", "vol", "model_err"):
                                parts[k] += x[k] * u
                        else:
                            parts["underlying_time_unsplit"] += x["mark"] * u
                    key = side if ok else "unattributed"
                    cnt[key] += 1
                    for k, v in parts.items():
                        agg[key][k] += v
                    agg[key]["execution"] += units_net - marks if ok else 0.
                    agg[key]["fees"] -= p["fees"]; agg[key]["net"] += p["net"]
            o[name] = {k: dict(tickets=cnt[k], **{kk: round(vv, 2) for kk, vv in v.items()}) for k, v in agg.items()}
        lib = defaultdict(list)
        for t in book:
            for r in L6.library(t):
                x = dict(zip(L6.LIBF, r))
                if x["status"] != 0 or x["R"] != 2500. or x["h"] != 8 or x["unresolved"] or x["e"] < 1:
                    continue
                z = L6.decompose(t, x["j"], x["i"], x["e"] - 1)
                if z and z["ok"]:
                    fav = "favourable" if x["d"] * z["dF"] > 0 else "adverse"
                    lib[("C" if x["d"] > 0 else "P", fav)].append((z["d_iv"], z["vol"], z["underlying"], z["time"]))
        o["library_iv"] = {f"{k[0]}|{k[1]}": dict(n=len(v), mean_d_iv=round(float(np.mean([a[0] for a in v])), 5),
                                                  vol_per_unit=round(float(np.mean([a[1] for a in v])), 4),
                                                  underlying_per_unit=round(float(np.mean([a[2] for a in v])), 4),
                                                  time_per_unit=round(float(np.mean([a[3] for a in v])), 4)) for k, v in sorted(lib.items()) if v}
        out[bk] = o
    return out


# ---------------------------------------------------------------- packets: EN70, EN58, EN56 on depth
def packets():
    P = PK.decode(); par = PK.parity(); dp, T1, T2 = PK.decision_parity()
    reasons = []
    if par["close_ok_share_vol"] < .95:
        reasons.append(f"option closes within 0.10 on {par['close_ok_share_vol']:.1%} of bars (< 95%)")
    if not par["future_independent_source"]:
        reasons.append("no independent futures (or index) minutes for the recorded days: the futures clause cannot be met")
    if not all(v["same"] for v in dp.values()):
        reasons.append("decisions differ between the recorder tape and the Breeze-options hybrid")
    en70 = dict(parity=par, decisions={k: dict(same=v["same"], recorder=v["recorder"], hybrid=v["hybrid"]) for k, v in dp.items()},
                verdict="PARITY PASS" if not reasons else "PARITY NOT ESTABLISHED", reasons=reasons)
    nov17 = {}
    for name in ("E032_30k", "EN55"):
        r = L6.run_day6(T1, L6.ARMS[name], "ordinary", 30000., L6.budget_of(L6.ARMS[name]), details=True)
        nov17[name] = dict(net=r["net"], trades=r["trades"], positions=[dict(decision_minute=int(T1.minute[p["decision_i"]]), side=p["direction"],
                                                                             lots=p["lots"], net=p["net"]) for p in r["positions"]])
    en70["nov17_ledgers"] = nov17
    intents, rows = PK.en58(T1, P)
    agg = {}
    for (tag, pol, proxy), rs in sorted(_group(rows, lambda r: (r["tag"], r["policy"], r["proxy"])).items()):
        fl = [r for r in rs if r.get("filled")]; un = [r for r in rs if not r.get("filled")]
        agg[f"{tag}|{pol}|{proxy}"] = dict(n=len(rs), filled=len(fl), how=dict(_count(r["how"] for r in rs)),
                                           cost_vs_mid=_mean([r.get("cost_vs_mid") for r in fl]), net_8min=round(sum(r["net"] for r in rs), 2),
                                           fill60=_mean([r.get("fill60") for r in fl]), fill180=_mean([r.get("fill180") for r in fl]),
                                           missed_winner=_mean([r.get("missed_winner") for r in un]),
                                           decision_mid180_filled=_mean([r.get("mid180") for r in fl]), decision_mid180_unfilled=_mean([r.get("mid180") for r in un]))
    en58 = dict(intents=[dict(minute=int(T1.minute[x["i"]]), d=x["d"], lots=x["lots"]) for x in intents], policies=agg,
                verdict="INCONCLUSIVE (one packet session)" + ("" if intents else "; EN55 made no intent on Nov 17"))
    lib = PK.en56_packets(T1, P)
    pkl = {}
    for (R_, h), rs in sorted(_group(lib, lambda r: (r["R"], r["h"])).items()):
        ok = [r for r in rs if r.get("pk_net") is not None]
        pkl[f"{int(R_)}|{h}"] = dict(rows=len(rs), packet_net_mean=_mean([r["pk_net"] for r in ok]), bar_net_mean=_mean([r["bar_net"] for r in ok]),
                                     packet_minus_bar=_mean([r["pk_net"] - r["bar_net"] for r in ok]),
                                     corr=round(float(np.corrcoef([r["pk_net"] for r in ok], [r["bar_net"] for r in ok])[0, 1]), 4) if len(ok) > 2 else None)
    return dict(EN70=en70, EN58=en58, EN56_packets=pkl)


# ---------------------------------------------------------------- entry points
def score():
    fz = json.loads(FREEZE.read_text())
    assert all(sha(p) == fz["files"][k] for k, p in _paths().items()), "frozen files changed"
    assert not git("status", "--porcelain", "--", *LOCAL_FILES, "freeze6.json"), "freeze not committed"
    assert not RESULTS.exists() and not START.exists(), "scored once"
    db = _data_bindings(); assert db == fz["data"], "data changed"
    START.write_text(json.dumps(dict(started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), freeze_head=fz["head"]), indent=2) + "\n")
    res, anat = pipeline(L6.books(), 40, fz["head"])
    RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8")
    ANAT.write_text(json.dumps(anat, indent=1, default=str) + "\n", encoding="utf-8")
    print("STATUS", json.dumps(res["status"]))


def selftest():
    L5.install(); B0 = L6.books(); B = {"NIFTY": B0["NIFTY"][:62], "SENSEX": B0["SENSEX"][:56]}
    res, anat = pipeline(B, 2, "selftest", quiet=True, boot=200, paths=50)
    json.dumps(res, default=str); json.dumps(anat, default=str)
    print("SELFTEST_OK", sorted(res["status"]), "arms", len(res["arms"]), "tests", len(res["tests"]))


if __name__ == "__main__":
    {"freeze": freeze, "score": score, "selftest": selftest}[sys.argv[1]]()
