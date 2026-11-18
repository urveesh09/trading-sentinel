"""EN71-EN85 scorer: PLAN7.md's frozen rules applied mechanically, once (development screen on seen sessions).

    python score7.py selftest   the whole pipeline on truncated books, short nulls and bootstrap; nothing written,
                                no rupees printed
    python score7.py freeze     hashes this round's files, every transitive frozen module (round 6's list), the
                                data bindings (round 6's, the all-session futures stores, the sealed OI exports, the
                                pinned engine tree, the N11 signal file, the pre-registration facts) -> freeze7.json,
                                and one registration.json per slot under registration/
    python score7.py score      refuses unless the freeze is committed and unchanged; start receipt; results7.json +
                                anatomy7.json, once"""
from __future__ import annotations
import hashlib, json, math, subprocess, sys, time
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-18-expiry-en56"))
import en_lab7 as L7  # noqa: E402
import prep7 as P7  # noqa: E402
import frontier7 as F7  # noqa: E402
import alloc7 as A7  # noqa: E402
import fut7  # noqa: E402
import en_score6 as S6  # noqa: E402

L6, L5, L4, L3, E = L7.L6, L7.L5, L7.L4, L7.L3, L7.E
LOCAL_FILES = ("PLAN7.md", "en_lab7.py", "prep7.py", "fut7.py", "n11x.py", "frontier7.py", "alloc7.py", "pk7.py", "check7.py", "score7.py", "fwd7.py",
               "n11-days.json", "n11-signals.json", "facts7.json", "erratum-en58-v2.json")
RESULTS, ANAT, START, FREEZE = HERE / "results7.json", HERE / "anatomy7.json", HERE / "results7-started.json", HERE / "freeze7.json"
SC = ("ordinary", "adverse", "catastrophe")
SEED = 20261119
EXTRA_FEE = 23.6                          # one more order: Rs 20 brokerage + 18% GST
FAMILY = tuple(f"{s}|{b}" for s in ("EN72", "EN73", "EN74", "EN75", "EN76", "EN77", "EN78", "EN79", "EN81", "EN82", "EN83", "EN84")
               for b in ("NIFTY", "SENSEX"))
UNAVAILABLE = {"EN74|NIFTY": "DATA UNAVAILABLE: no dated constituent weights or second-level constituent quotes",
               "EN74|SENSEX": "DATA UNAVAILABLE: no dated constituent weights or second-level constituent quotes",
               "EN77|NIFTY": "DATA UNAVAILABLE: no prospective timestamped news corpus with our receipt times",
               "EN77|SENSEX": "DATA UNAVAILABLE: no prospective timestamped news corpus with our receipt times",
               "EN83|SENSEX": "DATA UNAVAILABLE: SENSEX history carries zero open interest"}
CONTROL = "E03_env"
INFO = ("EN73", "EN75", "EN76", "EN78", "EN83")          # new-information setups: must beat their random-side null's 90th pct
FULL = [k for k in L7.ARMS]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git(*a):
    return subprocess.run(("git",) + a, cwd=HERE, capture_output=True, text=True).stdout.strip()


def _paths():
    fz6 = json.loads((HERE.parent / "2026-11-18-expiry-en56" / "freeze6.json").read_text())
    ext = {f"round6/{k}": p for k, p in S6._paths().items()}
    return {**{f: HERE / f for f in LOCAL_FILES}, **ext}, fz6


def _data_bindings():
    import n11x
    d6 = S6._data_bindings()
    sig = HERE / "n11-signals.json"
    return dict(round6=d6, fut7={u: fut7.store(u)["manifest"] for u in ("NIFTY", "SENSEX")},
                sealed_oi={k: sha(v) for k, v in sorted({str(p): p for p in P7.SEALED.values()}.items())},
                pinned_tree_sha256=n11x.tree_sha(), n11_signals_sha256=sha(sig) if sig.exists() else None,
                facts7_sha256=sha(HERE / "facts7.json"))


def registration():
    """One registration.json per slot: arms (rule dumps + hashes), the cohort and the classification, before scoring."""
    reg = HERE / "registration"; reg.mkdir(exist_ok=True)
    slots = defaultdict(dict)
    for name, arm in L7.ARMS.items():
        slot = name.split("_")[0] if name.startswith("EN") else "CONTROL"
        d = asdict(arm); slots[slot][name] = dict(rule=d, hash=hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16])
    cohort = dict(start=dict(SENSEX="2026-11-19", NIFTY="2026-11-23"), scheduled_review="first 40 eligible expiries per index",
                  continue_to="100 eligible expiries per index if support is short", support="20 executed parents over >= 10 traded expiries per index",
                  missing="a session lacking required evidence is MISSING, never a zero no-trade day; coverage sensitivity reported",
                  classification=["INCOME CANDIDATE", "TAIL CANDIDATE", "PROTECTION CANDIDATE", "FAIL", "INCONCLUSIVE", "DATA UNAVAILABLE"],
                  data="Breeze index + front future + expiring chain 12:00-15:29 per expiry via the download skill (request 7)")
    extra = {"EN71": dict(kind="diagnostic", code=["frontier7.py", "pk7.py"], predictors=list(F7.PS), delays=list(F7.DELAYS), hold=F7.HOLD,
                          ceilings=["C1 direction known (untradeable)", "C2 best executable action at a fixed clock (untradeable)", "C3 EN56 whole-day maximum (untradeable)"]),
             "EN74": dict(kind="DATA UNAVAILABLE", capture_contract="top-ten constituents by dated official weight + index future + chain on one receipt clock; >= 95% windows with quote age <= 2 s; 60 prior sessions"),
             "EN77": dict(kind="DATA UNAVAILABLE", capture_contract="RBI decisions + top-ten-weight results: document, first public time, our first receipt time, revisions; >= 20 releases on 10 expiries"),
             "EN79": dict(kind="adaptive selector", code=["alloc7.py"], experts=list(A7.EXPERTS), eta=A7.ETA, log_weight_cap=A7.CAP, tie="CASH then listed order"),
             "EN80": dict(kind="integration engine", code=["alloc7.py"], eligible_now=[], combined_policy="EN72-EN78 variants passing forward criteria only; earliest signal, slot number tie-break; one open position; Rs 2,500 room"),
             "EN85": dict(kind="forward machine", code=["fwd7.py"], ledger="forward7/ledger.jsonl", review_at=40, continue_to=100)}
    for slot, body in extra.items():
        slots.setdefault(slot, {})["_definition"] = body
    out = {}
    for slot, arms in sorted(slots.items()):
        body = dict(slot=slot, arms=arms, cohort=cohort, plan="PLAN7.md", registered_before_any_score=True)
        (reg / f"{slot}.json").write_text(json.dumps(body, indent=1, default=str) + "\n", encoding="utf-8"); out[slot] = sha(reg / f"{slot}.json")
    return out


def freeze():
    assert not RESULTS.exists() and not START.exists()
    paths, fz6 = _paths()
    for k, p in S6._paths().items():
        assert fz6["files"][k] == sha(p), f"round-6 frozen file changed: {k}"
    regs = registration()
    FREEZE.write_text(json.dumps(dict(files={k: sha(p) for k, p in paths.items()}, data=_data_bindings(), registrations=regs, head=git("rev-parse", "HEAD")),
                                 indent=2, default=str) + "\n")
    print("FROZEN", git("rev-parse", "HEAD"))


# ---------------------------------------------------------------- statistics (PLAN7 s.3)
def week(day):
    y, w, _ = date.fromisoformat(day).isocalendar()
    return (y, w)


def blocks(days, x):
    """Calendar-week block sums and session counts (every session, zero days included)."""
    s = defaultdict(float); n = defaultdict(int)
    for d, v in zip(days, x):
        s[week(d)] += v; n[week(d)] += 1
    k = sorted(s)
    return np.array([s[q] for q in k]), np.array([n[q] for q in k])


def signflip_p(bs, B, seed):
    """One-sided randomisation test of a positive paired mean: signs of whole calendar-week blocks flipped."""
    if len(bs) == 0 or not np.any(bs):
        return 1.
    rng = np.random.default_rng(seed); obs = bs.sum(); hit = 0
    for s in range(0, B, 5000):
        k = min(5000, B - s); f = rng.choice((-1., 1.), (k, len(bs))); hit += int(np.sum(f @ bs >= obs - 1e-9))
    return float((1 + hit) / (B + 1))


def block_ci(bs, ns, B, seed):
    """95% percentile interval of the mean per session, resampling calendar-week blocks."""
    if len(bs) == 0:
        return (0., 0.)
    rng = np.random.default_rng(seed); m = np.empty(B)
    for s in range(0, B, 5000):
        k = min(5000, B - s); idx = rng.integers(0, len(bs), (k, len(bs))); m[s:s + k] = bs[idx].sum(1) / ns[idx].sum(1)
    return (round(float(np.percentile(m, 2.5)), 2), round(float(np.percentile(m, 97.5)), 2))


def holm(ps):
    keys = sorted(ps, key=lambda k: ps[k]); m = len(keys); adj = {}; run = 0.
    for r, k in enumerate(keys):
        run = max(run, min(1., (m - r) * ps[k])); adj[k] = round(run, 4)
    return adj


def _seed(h):
    return SEED + 10 * FAMILY.index(h)


def paired(cand, ctrl, B, seed):
    days = [d["day"] for d in cand]; assert days == [d["day"] for d in ctrl]
    diff = [a["net"] - b["net"] for a, b in zip(cand, ctrl)]
    bs, ns = blocks(days, diff); cb, cn = blocks(days, [a["net"] for a in cand])
    top = sorted(range(len(cand)), key=lambda i: -cand[i]["net"])[:2]
    return dict(diff_per_session=round(float(np.mean(diff)), 2), diff_total=round(float(np.sum(diff)), 2), ci=block_ci(bs, ns, B, seed),
                p_vs_control=signflip_p(bs, B, seed), p_vs_cash=signflip_p(cb, B, seed + 1), ci_vs_cash=block_ci(cb, cn, B, seed + 1),
                diff_without_top2=round(float(sum(diff[i] for i in range(len(diff)) if i not in top)), 2), weeks=len(bs))


# ---------------------------------------------------------------- measurement
def metrics(days):
    m = S6.metrics(days)
    m["minutes_in"] = int(sum(d.get("minutes_in", 0) for d in days))
    m["traded_expiries"] = m.pop("expiries")
    return m


def run_arm(name, arm, book, by, details_ord=True):
    out = {}; keep = {}
    for sc in SC:
        days = [L7.day7(t, arm, sc, 30000., L7.budget_of(arm), details_ord and sc == "ordinary") for t in book]
        for d in days:
            d["und"] = L7.und(book[0])
        out[sc] = metrics(days); keep[sc] = days
        if sc == "ordinary" and details_ord:
            out["tickets"] = S6.tmetrics(S6.tickets(days, by))
    for sc in ("ordinary", "adverse"):
        w = L7.run_wallet7(book, arm, sc)
        out[f"wallet|{sc}"] = dict(S6.wallet_view(w), combined=round(w["wallet"] + w["swept"], 2))
    return out, keep


def stressed(arm, book):
    out = {}
    with L7.stress(extra_fee=EXTRA_FEE):
        out["extra_order_fee"] = metrics([L7.day7(t, arm, "ordinary", 30000., L7.budget_of(arm), False) for t in book])["net"]
    with L7.stress(sell_delay=1):
        out["missed_exits"] = metrics([L7.day7(t, arm, "ordinary", 30000., L7.budget_of(arm), False) for t in book])["net"]
    if isinstance(arm, L7.Rule) and not arm.entry_delay:
        a1 = replace(arm, entry_delay=1)
        out["entry_one_bar_late"] = metrics([L7.day7(t, a1, "ordinary", 30000., L7.budget_of(a1), False) for t in book])["net"]
    return out


def nulls(arm, book, seeds):
    v = []
    for s in range(seeds):
        L3.NULL = f"R7-{s}"
        try:
            v.append(sum(L7.day7(t, arm, "ordinary", 30000., L7.budget_of(arm), False)["net"] for t in book))
        finally:
            L3.NULL = None
    v = np.array(v)
    return dict(seeds=seeds, median=round(float(np.median(v)), 2), p90=round(float(np.percentile(v, 90)), 2), mean=round(float(v.mean()), 2))


def classify(h, m_ord, m_adv, st, n_ctrl, w_c, w_k, null=None):
    """PLAN7 s.3, development screen. m_*: metrics; st: paired stats (with holm); n_ctrl: control metrics."""
    if m_ord["tickets"] < 20 or m_ord["traded_expiries"] < 10:
        return "INCONCLUSIVE (support below 20 parents over 10 traded expiries)"
    side_ok = null is None or m_ord["net"] > null["p90"]
    inc = (m_ord["net"] > 0 and m_adv["net"] > 0 and st["ci"][0] > 0 and st["holm"] <= .05 and st["ci_vs_cash"][0] > 0
           and m_ord["without_top2"] > 0 and st["diff_without_top2"] > 0)
    if inc and side_ok:
        return "INCOME-LIKE (development screen)"
    tail = m_ord["net"] > 0 and m_adv["net"] > 0 and st["diff_per_session"] > 0 and st["tail_wins"] >= 3
    if tail and side_ok:
        return "TAIL-LIKE (development screen)"
    cost = (n_ctrl["net"] - m_ord["net"]) / max(1, m_ord["sessions"])
    if m_ord["worst"] >= n_ctrl["worst"] and w_c["liq_dd"] < w_k["liq_dd"] and cost <= 25.:
        return "PROTECTION-LIKE (development screen)"
    return "FAIL" + ("" if side_ok else " (side information not shown: below the random-side null's 90th percentile)")


def scout_anatomy(cand, ctrl):
    """EN72 against matched E03: split vs indivisible one-lot parents, adds bought, and the P&L split into matched
    parents (same decision bar and side: fee and price/size parts) and changed admissions."""
    out = dict(parents=0, split=0, one_lot=0, adds=0, first_lots=0, planned_lots=0, matched=0, matched_dnet=0., matched_dfees=0.,
               only_candidate=0, only_candidate_net=0., only_control=0, only_control_net=0.)
    for x, y in zip(cand, ctrl):
        kx = {(p["decision_i"], p["direction"]): p for p in x["positions"]}; ky = {(p["decision_i"], p["direction"]): p for p in y["positions"]}
        for k, p in kx.items():
            buys = [e for e in p["events"] if e["side"] == "BUY"]; out["parents"] += 1
            out["first_lots"] += buys[0]["lots"] if buys else 0; out["adds"] += max(0, len(buys) - 1)
            pl = p.get("planned") or (buys[0]["lots"] + (p.get("add_lots_planned") or 0) if buys else 0)
            out["split" if p.get("add_lots_planned", 0) or len(buys) > 1 or (p.get("planned") or 0) >= 2 else "one_lot"] += 1
            if k in ky:
                out["matched"] += 1; out["matched_dnet"] += p["net"] - ky[k]["net"]; out["matched_dfees"] += p["fees"] - ky[k]["fees"]
            else:
                out["only_candidate"] += 1; out["only_candidate_net"] += p["net"]
        for k, p in ky.items():
            if k not in kx:
                out["only_control"] += 1; out["only_control_net"] += p["net"]
    return {k: round(v, 2) if isinstance(v, float) else v for k, v in out.items()}


def diagnostics(B, keep=None):
    """Mechanism records of the new-information setups (no verdicts)."""
    out = {}
    for bk, book in B.items():
        d = {}
        if keep and ("EN72", bk) in keep:
            d["EN72_scout"] = scout_anatomy(keep[("EN72", bk)]["ordinary"], keep[(CONTROL, bk)]["ordinary"])
        n11m = [L7.N11.get((bk, t.day)) for t in book]
        mfr = []
        for t, r in zip(book, n11m):
            if r and not r.get("missing"):
                for s in r["signals"]:
                    if s["d"] and 585 <= s["m"] < 720 and s["m"] - 556 + 8 < 375:
                        k = s["m"] - 556
                        if np.isfinite(t.f[[k, k + 8], 3]).all():
                            mfr.append(s["d"] * (t.f[k + 8, 3] - t.f[k, 3]))
        d["EN76_morning_signal_only"] = dict(signals=len(mfr), fut8_mean=round(float(np.mean(mfr)), 2) if mfr else None,
                                             note="09:45-12:00 signals; options untestable (tapes hold the chain from 12:00 only)")
        ev = [e for t in book for e in L7.META7.get(("SYNF75", bk, t.day), [])]
        def mean(xs):
            xs = [x for x in xs if x is not None]
            return round(float(np.mean(xs)), 3) if xs else None
        d["EN75"] = dict(events=len(ev), future_toward_1=mean([float(e["dF1"] > 0) for e in ev if "dF1" in e]),
                         future_toward_3=mean([float(e["dF3"] > 0) for e in ev if "dF3" in e]), dF3_points=mean([e.get("dF3") for e in ev]),
                         dX3_points=mean([e.get("dX3") for e in ev]), options_came_back_3=mean([float(e["dB3"] < 0) for e in ev if "dB3" in e]),
                         dB3_points=mean([e.get("dB3") for e in ev]), dF8_points=mean([e.get("dF8") for e in ev]))
        ev = [e for t in book for e in L7.META7.get(("BASIS78", bk, t.day), [])]
        rep = [e for e in ev if e.get("repair8") is not None]
        d["EN78"] = dict(events=len(ev), entered=sum(e["entered"] is not None for e in ev), repaired8=mean([float(e["repair8"] > 0) for e in rep]),
                         repair8_points=mean([e["repair8"] for e in rep]), cash_share_median=(round(float(np.median([e["cash_share"] for e in rep if e.get("cash_share") is not None])), 3)
                                                                                                if any(e.get("cash_share") is not None for e in rep) else None),
                         cash_led=mean([float(e["cash_share"] > .5) for e in rep if e.get("cash_share") is not None]))
        if bk == "NIFTY":
            ev = [e for t in book for e in L7.META7.get(("OI83", bk, t.day), [])]
            d["EN83"] = dict(events=len(ev), agrees_with_price=mean([e["agree_px"] for e in ev]), threshold_median=mean([e["th"] for e in ev]))
        sc = L7.META7.get(("RIDGE73_scores", bk), [])
        if sc:
            by = defaultdict(list)
            for r in sc:
                by[r["day"]].append(r)
            def mse(k):
                return float(np.mean([np.mean([(r["y"] - r[k]) ** 2 for r in v]) for v in by.values() if all(r[k] is not None for r in v)]))
            ic = [np.corrcoef([r["y"] for r in v], [r["ridge"] for r in v])[0, 1] for v in by.values() if len(v) >= 5]
            ic = [x for x in ic if np.isfinite(x)]
            sign = float(np.mean([np.mean([np.sign(r["y"]) == np.sign(r["ridge"]) for r in v if r["y"] != 0]) for v in by.values()]))
            d["EN73_forecast"] = dict(expiries=len(by), rows=len(sc), mse_ridge=mse("ridge"), mse_icpt=mse("icpt"),
                                      mse_ratio=round(mse("ridge") / mse("icpt"), 4), ic_mean=round(float(np.mean(ic)), 4) if ic else None,
                                      sign_hit=round(sign, 4), note="genuinely forward: each expiry's windows never trained or calibrated its model")
            vv = [e for t in book for e in L7.META7.get(("RIDGE73", bk, t.day), []) if e.get("actual")]
            err = [(e["V"] - e["actual"]) / e["actual"] for e in vv if e["actual"] > 0]
            d["EN73_value_error"] = dict(n=len(err), median_rel=round(float(np.median(err)), 4) if err else None,
                                         mean_abs_rel=round(float(np.mean(np.abs(err))), 4) if err else None)
        n11 = [L7.N11.get((bk, t.day)) for t in book]
        sig = [(t, s) for t, r in zip(book, n11) if r and not r.get("missing") for s in r["signals"] if s["d"] and 780 <= s["m"] < 870]
        strat = defaultdict(int); why = defaultdict(int); fr = []
        for t, s in sig:
            strat[s["strategy"]] += 1
            i = int(np.searchsorted(t.minute, s["m"]))
            if i + 8 < t.n and np.isfinite(t.f[[i, i + 8], 3]).all():
                fr.append(s["d"] * (t.f[i + 8, 3] - t.f[i, 3]))
        for r in n11:
            if r and not r.get("missing"):
                for s in r["signals"]:
                    if 780 <= s["m"] < 870 and not s["d"]:
                        why[s["why"].split(":")[0]] += 1
        d["EN76"] = dict(days=sum(1 for r in n11 if r and not r.get("missing")), missing=sum(1 for r in n11 if not r or r.get("missing")),
                         signals=len(sig), strategies=dict(strat), reject=dict(sorted(why.items(), key=lambda x: -x[1])[:8]),
                         signal_only_fut8_mean=round(float(np.mean(fr)), 2) if fr else None, signal_only_fut8_right=round(float(np.mean([x > 0 for x in fr])), 3) if fr else None,
                         adx_high_days=sum(1 for t in book if (L7.GATE7.get(("ADX", t.day)) or 0) >= 30))
        out[bk] = d
    # EN76's control: the same signal on normal NIFTY afternoons (signal-only futures returns; no option quotes exist)
    nr = [r for (u, d_), r in L7.N11.items() if u == "NIFTY" and r.get("from_min") == 750 and not r.get("missing")]
    fr = []
    for r in nr:
        s_ = fut7.store("NIFTY"); F = s_["F"][s_["pos"][r["day"]]][:, 3]
        for s in r["signals"]:
            if s["d"] and 780 <= s["m"] < 870:
                k = s["m"] - 556
                if k + 8 < 375 and np.isfinite(F[[k, k + 8]]).all():
                    fr.append(s["d"] * (F[k + 8] - F[k]))
    out["EN76_normal_days"] = dict(days=len(nr), signals=len(fr), signal_only_fut8_mean=round(float(np.mean(fr)), 2) if fr else None,
                                   signal_only_fut8_right=round(float(np.mean([x > 0 for x in fr])), 3) if fr else None)
    return out


def harness(book, by, B, pairs=20):
    """Calibration of the paired test under nulls: pairs of independent random-entry E03 controls (both null)."""
    ps = []; ps_eff = []; cover = 0
    for k in range(pairs):
        res = []
        for tag in ("A", "B"):
            L4.RANDOM = f"H7-{tag}-{k}"
            try:
                res.append([L7.day7(t, L7.E03_ENV, "ordinary", 30000., 2500., False) for t in book])
            finally:
                L4.RANDOM = None
        a, b = res; days = [d["day"] for d in a]
        diff = np.array([x["net"] - y["net"] for x, y in zip(a, b)])
        bs, ns = blocks(days, diff); ps.append(signflip_p(bs, B, SEED + k))
        eff = diff + np.array([100. if x["trades"] else 0. for x in a])                # a known +Rs 100 per traded session
        be, _ = blocks(days, eff); ps_eff.append(signflip_p(be, B, SEED + 100 + k))
        lo, hi = block_ci(bs, ns, B, SEED + 200 + k); cover += lo <= 0 <= hi
    return dict(pairs=pairs, null_rejections_at_05=int(sum(p <= .05 for p in ps)), null_p=[round(p, 3) for p in ps],
                known_effect_detected_at_05=int(sum(p <= .05 for p in ps_eff)), ci_covers_zero_under_null=cover)


# ---------------------------------------------------------------- the round
def pipeline(B, seeds, B_boot, quiet=False, head=None):
    T0 = time.time()
    log = (lambda *a: None) if quiet else (lambda *a: print(f"[{time.time() - T0:7.0f}s]", *a, flush=True))
    if head:
        B = {"NIFTY": B["NIFTY"][:head], "SENSEX": B["SENSEX"][:max(10, head // 3)]}
    info = P7.prepare(B); log("prepared", info and info["pinned_tree_sha256"][:12])
    by = S6.daymap(B)
    res = dict(arms={}, n11=info); keep = {}
    for name in FULL:
        for bk, book in B.items():
            if name.startswith("EN83") and bk == "SENSEX":
                continue
            out, kp = run_arm(name, L7.ARMS[name], book, by)
            res["arms"][f"{name}|{bk}"] = out; keep[(name, bk)] = kp
        log("arm", name)
    # EN79
    res["EN79"] = {}
    for bk, book in B.items():
        r = A7.en79(book)
        for sc in ("adverse",):
            ra = A7.en79(book, sc); keep[("EN79", bk, sc)] = ra["days"]["EN79"]
        w = A7.selector_wallet(book, r["receipts"]); wa = A7.selector_wallet(book, r["receipts"], "adverse")
        res["EN79"][bk] = dict(chosen=r["chosen"], best_fixed=r["best_fixed"], totals=r["totals"], missed_winners=r["missed_winners"][:20],
                               missed_winner_count=len(r["missed_winners"]),
                               controls={k: metrics(v) for k, v in r["days"].items()},
                               wallet=dict(P=w["P"], swept=w["swept"], wallet=w["wallet"], halted=w["halted"], first_halt=w["first_halt"], liq_dd=w["liq_dd"]),
                               wallet_adverse=dict(P=wa["P"], halted=wa["halted"], first_halt=wa["first_halt"]),
                               receipts=[dict(day=x["day"], chosen=x["chosen"], pre={k: round(v, 4) for k, v in x["pre"].items()}) for x in r["receipts"]])
        keep[("EN79", bk)] = r["days"]["EN79"]
        res["arms"][f"EN79|{bk}"] = dict(ordinary=metrics(r["days"]["EN79"]), adverse=metrics(keep[("EN79", bk, "adverse")]),
                                          **{"wallet|ordinary": dict(liq_dd=w["liq_dd"], P=w["P"], halted=w["halted"])})
    log("EN79")
    res["EN80"] = A7.en80(B, {"NIFTY": "E03_env", "SENSEX": "E03_env"}); log("EN80")
    # hypotheses
    hyp = {}; raw = {}
    for h in FAMILY:
        slot, bk = h.split("|")
        if h in UNAVAILABLE:
            hyp[h] = dict(verdict=UNAVAILABLE[h]); raw[h] = 1.; continue
        cand = keep[("EN79", bk)] if slot == "EN79" else keep[(slot, bk)]["ordinary"]
        ctrl = keep[(CONTROL, bk)]["ordinary"]
        st = paired(cand, ctrl, B_boot, _seed(h)); raw[h] = st["p_vs_control"]
        st["tail_wins"] = len({d["day"] for d in cand if d["net"] >= 2500})
        hyp[h] = st
    adj = holm(raw)
    for h in FAMILY:
        if h in UNAVAILABLE:
            continue
        slot, bk = h.split("|"); st = hyp[h]; st["holm"] = adj[h]
        m = res["arms"][f"{slot}|{bk}"]; mc = res["arms"][f"{CONTROL}|{bk}"]
        null = None
        if slot in INFO:
            null = nulls(L7.ARMS[slot], B[bk], seeds); st["null"] = null
        wk = m.get("wallet|ordinary", {}); wc = mc["wallet|ordinary"]
        st["verdict"] = classify(h, m["ordinary"], m["adverse"], st, mc["ordinary"], dict(liq_dd=wk.get("liq_dd", 1e9)), wc, null)
        if slot != "EN79":
            st["stress"] = stressed(L7.ARMS[slot], B[bk])
            st["changed_parents_vs_control"] = S6.affected(keep[(slot, bk)]["ordinary"], keep[(CONTROL, bk)]["ordinary"])
    res["hypotheses"] = hyp; log("verdicts")
    res["diagnostics"] = diagnostics(B, keep); log("diagnostics")
    res["EN71"] = {}
    for bk, book in B.items():
        fr, rows = F7.frontier(book)
        lib = [r for t in book for r in L6.library(t)]
        f8 = [r for r in lib if r[4] == 2500. and r[7] == 8 and r[6] == L6.ST["FILLED"]]
        fr["library_reproduced"] = dict(rows=len(lib), filled_2500_h8=len(f8), net_mean_2500_h8=round(float(np.mean([r[9] for r in f8])), 2) if f8 else None,
                                        paired_side=F7.paired_side_share(f8))
        res["EN71"][bk] = fr
    if not head:
        import pk7
        res["EN71"]["packet_pilot"] = F7.packet_pilot()
        res["EN75_packet_pilot"] = pk7.en75_pilot(); res["EN78_packet_pilot"] = pk7.en78_pilot()
    log("EN71")
    import fwd7
    res["EN85_power"] = fwd7.power({k: v for k, v in res["arms"].items() if isinstance(v, dict) and "ordinary" in v and "tickets" in v["ordinary"]})
    res["harness"] = harness(B["NIFTY"], by, B_boot, pairs=20 if not head else 3); log("harness")
    anat = {f"{k[0]}|{k[1]}": [dict(day=d["day"], net=d["net"], trades=d["trades"], fees=d["fees"], marked_worst=d.get("marked_worst"),
                                    minutes_in=d.get("minutes_in", 0)) for d in v["ordinary"]] for k, v in keep.items() if len(k) == 2 and isinstance(v, dict)}
    for bk in B:
        anat[f"EN79|{bk}"] = [dict(day=d["day"], net=d["net"], trades=d["trades"], expert=d.get("expert")) for d in keep[("EN79", bk)]]
    tick = {f"{k[0]}|{k[1]}": S6.tickets(v["ordinary"], by) for k, v in keep.items() if len(k) == 2 and isinstance(v, dict)
            and (k[0] in L7.PRIMARY or k[0] in (CONTROL, "E032_30k", "EN55"))}
    return res, dict(days=anat, tickets=tick)


def score():
    assert FREEZE.exists() and not RESULTS.exists() and not START.exists()
    fz = json.loads(FREEZE.read_text()); paths, _ = _paths()
    bad = [k for k, p in paths.items() if fz["files"].get(k) != sha(p)]
    assert not bad, f"changed since freeze: {bad}"
    assert not git("status", "--porcelain", "--", *[str(HERE / f) for f in LOCAL_FILES]), "commit the frozen files first"
    assert fz["data"] == json.loads(json.dumps(_data_bindings(), default=str)), "data bindings changed"
    START.write_text(json.dumps(dict(started=time.strftime("%Y-%m-%d %H:%M:%S"), head=git("rev-parse", "HEAD"), freeze_sha256=sha(FREEZE)), indent=1) + "\n")
    L5.install(); B = L6.books()
    res, anat = pipeline(B, seeds=40, B_boot=20000)
    RESULTS.write_text(json.dumps(res, indent=1, default=float) + "\n", encoding="utf-8")
    ANAT.write_text(json.dumps(anat, default=float) + "\n", encoding="utf-8")
    print("STATUS", json.dumps({h: v.get("verdict") for h, v in res["hypotheses"].items()}))


def selftest():
    L5.install(); B = L6.books()
    res, anat = pipeline(B, seeds=2, B_boot=500, quiet=True, head=24)
    json.dumps(res, default=float); json.dumps(anat, default=float)
    print("SELFTEST_OK hypotheses", len(res["hypotheses"]), "arms", len(res["arms"]), "EN71 keys", sorted(res["EN71"]))


if __name__ == "__main__":
    {"freeze": freeze, "score": score, "selftest": selftest}[sys.argv[1]]()
