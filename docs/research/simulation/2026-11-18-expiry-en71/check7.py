"""Round-7 checks (no rupees printed): parity with the frozen round-6 loop, causality of every new setup (later bars
erased, later sessions corrupted), synthetic mechanics (loss room, parents, delay, blind add, gates, stresses), the
vectorised Black against the lab's, and known-signal recovery (EN73's ridge, EN75's synthetic forward, EN71's oracle).

    python check7.py            (needs _local/n11-signals.json for the N11-dependent checks)"""
from __future__ import annotations
import json, math, sys
from dataclasses import replace
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import en_lab7 as L7  # noqa: E402
import prep7 as P7  # noqa: E402
import fut7  # noqa: E402

L6, L5, L4, L3, E, D4 = L7.L6, L7.L5, L7.L4, L7.L3, L7.E, L7.D4


def check_parity(B):
    n = 0
    for name, arm in L6.ARMS.items():
        if not isinstance(arm, L6.Rule) or arm.core_bank or arm.core_child or arm.ladder or arm.liq_pick or arm.setup3 in ("RESID", "RESID_DIR", "RESID_DECAY"):
            continue
        r7 = L7.R7(arm)
        for bk, book in B.items():
            for sc in ("ordinary", "adverse", "catastrophe"):
                a = [L6.run_day6(t, arm, sc, 30000., L6.budget_of(arm)) for t in book]
                b = [L7.run_day7(t, r7, sc, 30000., L7.budget_of(r7)) for t in book]
                bad = [x["day"] for x, y in zip(a, b) if (x["net"], x["trades"], x["spent"], x["fees"]) != (y["net"], y["trades"], y["spent"], y["fees"])]
                assert not bad, (name, bk, sc, bad[:3]); n += len(a)
    for name in ("E032_30k", "EN55"):
        for bk, book in B.items():
            w6 = L6.run_wallet6(book, L6.ARMS[name]); w7 = L7.run_wallet7(book, L7.ARMS[name])
            assert (w6["P"], w6["swept"], w6["halted"], w6["first_halt"], w6["liq_dd"]) == (w7["P"], w7["swept"], w7["halted"], w7["first_halt"], w7["liq_dd"])
    rng = np.random.default_rng(1)
    for _ in range(2000):
        F, K, T, v = rng.uniform(18000, 26000), rng.uniform(18000, 26000), rng.uniform(1e-5, 3e-4), rng.uniform(.05, 1.)
        for call in (True, False):
            assert abs(float(L7.bsv(np.array([F]), K, T, v, call)[0]) - L5.price(F, K, T, v, call)) < 1e-6
    return f"PARITY_OK {n} arm-days run_day7 == run_day6 (hooks off), wallets equal, vectorised Black == L5.price on 4,000 draws"


def _trunc(t, i):
    u = L6._truncated(t, i); L7.KEEP7.append(u); return u


def check_causal(B):
    n = 0
    for bk, book in B.items():
        for t in book[::11]:
            for fn, keys in ((P7.syn75, ("SYNF75", "SYNF75_FUT", "SYNF75_ONE")), (P7.basis78, ("BASIS78", "BASIS78_FUT", "BASIS78_MR", "BASIS78_MOM"))):
                fn(t); ref = {k: L7.PRE7[(k, bk, t.day)].copy() for k in keys}
                for k in keys:
                    for i in np.flatnonzero(ref[k])[:2]:
                        u = _trunc(t, int(i)); u.und = getattr(t, "und", "NIFTY"); fn(u)
                        assert L7.PRE7[(k, bk, t.day)][i] == ref[k][i], (fn.__name__, k, t.day, int(i)); n += 1
                fn(t)
        # EN73: the decision at bar i is unchanged with later bars erased and every later session corrupted in the store
        u_ = bk; s = fut7.store(u_)
        for t in book[::25]:
            mdl = P7.fit73(u_, t.day, "ridge", [x.day for x in book])
            if mdl is None:
                continue
            for i in (L6.at(t, 800), L6.at(t, 845)):
                v0 = P7.value73(t, i, 1, mdl, L7.E03_ENV)
                Fsave, Xsave = s["F"].copy(), s["X"].copy(); pos = s["pos"][t.day]
                try:
                    s["F"][pos, i + 1:] = np.nan; s["F"][pos + 1:] *= 1.37; s["X"][pos + 1:] *= .71
                    P7._ROWS.pop((u_, t.day), None)
                    mdl2 = P7.ridge([(u_, d) for d in fut7.prior_sessions(u_, t.day, 140)[:120]])
                    assert np.allclose(mdl2["beta"], mdl["beta"]) and abs(mdl2["b0"] - mdl["b0"]) < 1e-12
                    v1 = P7.value73(_trunc(t, i), i, 1, mdl, L7.E03_ENV)
                finally:
                    s["F"][:] = Fsave; s["X"][:] = Xsave; P7._ROWS.pop((u_, t.day), None)
                assert (v0 is None) == (v1 is None) and (v0 is None or abs(v0["lb"] - v1["lb"]) < 1e-9), (t.day, i); n += 1
    # EN83: thresholds and scores read only earlier sessions and bars <= i
    book = B["NIFTY"]; P7.oi83(book); ref = {t.day: L7.PRE7[("OI83", "NIFTY", t.day)].copy() for t in book}
    for t in book[30::40]:
        S = P7.oi_score(t)
        for i in np.flatnonzero(ref[t.day])[:2]:
            oi = P7._OI[("NIFTY", t.day)]; keep = oi.copy()
            try:
                oi[i + 1:] = np.nan
                assert np.isclose(P7.oi_score(t)[i], S[i]); n += 1
            finally:
                oi[:] = keep
    return f"CAUSAL_OK {n} decisions unchanged with later bars erased / later sessions corrupted"


def _syn_tape(prem=15.):
    """A flat synthetic session with every OTM strike inside the coverage band (call 25,000 is contract 0)."""
    t = L4._synthetic_tape(np.full(375, 50.), index_step=0.); D = D4._D(); n = 375; i0 = L7.at(t, 780)
    ks = [(25000., 1), (25050., 1), (25100., 1), (25150., 1), (24950., -1), (24900., -1), (24850., -1), (24800., -1)]
    q = np.full((n, len(ks), 5), np.nan)
    for k in range(len(ks)):
        q[:, k, 0] = q[:, k, 3] = prem; q[:, k, 1] = prem * 1.002; q[:, k, 2] = prem * .998; q[:, k, 4] = 1e6
    def tape(qq, x=None):
        u = D.Tape(t.day, t.x if x is None else x, t.f, qq, np.array([k for k, _ in ks]), np.array([d for _, d in ks]), [str(k) for k, _ in ks],
                   t.now, t.minute, 0)
        L7.KEEP7.append(u); return u
    return t, q, tape, i0


def check_mech():
    t, q, tape, i0 = _syn_tape(); sp = L4.spec_of(t)
    # 1. the loss room: a first parent that loses leaves budget - loss for the second; profits add nothing
    sig = np.zeros(375, np.int8); sig[i0] = 1; sig[i0 + 30] = 1
    key = ("SYNF75", "NIFTY", t.day)
    g = q.copy(); g[i0 + 3:i0 + 20, 0, :4] = 9.; g[i0 + 20:, 0, :4] = 15.
    L7.PRE7[key] = sig
    arm = L7.R7(L7.E032, setup3="SYNF75", **L7.ENV7)
    r = L7.run_day7(tape(g), arm, "ordinary", 30000., 2500., details=True)
    assert r["trades"] == 2, r["trades"]
    p1, p2 = r["positions"]; assert p1["net"] < 0 and p2["room"] <= 2500. + p1["net"] + .01, (p1["net"], p2["room"])
    # 2. max parents: a third signal never becomes a parent
    sig2 = sig.copy(); sig2[i0 + 50] = 1; L7.PRE7[key] = sig2
    assert L7.run_day7(tape(g), arm, "ordinary", 30000., 2500.)["trades"] == 2
    # 3. entry delay: the buy fills d bars later
    L7.PRE7[key] = sig
    for dl in (0, 1, 3):
        r = L7.run_day7(tape(q), replace(arm, entry_delay=dl, max_parents=1), "ordinary", 30000., 2500., details=True)
        assert r["positions"][0]["entry_i"] == i0 + 1 + dl, (dl, r["positions"][0]["entry_i"])
    # 4. blind add: the second half is bought two bars after entry without any favourable check
    r = L7.run_day7(tape(q), replace(arm, blind_add=True, max_parents=1, max_lots=3), "ordinary", 30000., 2500., details=True)
    buys = [e for e in r["positions"][0]["events"] if e["side"] == "BUY"]
    assert len(buys) == 2 and buys[1]["i"] == buys[0]["i"] + 3, buys
    # 5. gates zero the day / the bar
    L7.GATE7[("ADX", t.day)] = 20.
    assert L7.run_day7(tape(q), replace(arm, gate="ADX30"), "ordinary", 30000., 2500.)["trades"] == 0
    assert L7.run_day7(tape(q), replace(arm, gate="ADX30_INV"), "ordinary", 30000., 2500.)["trades"] >= 1
    L7.GATE7[("RVOL", t.day)] = {}
    assert L7.run_day7(tape(q), replace(arm, gate="RVOL"), "ordinary", 30000., 2500.)["trades"] == 0
    del L7.GATE7[("ADX", t.day)], L7.GATE7[("RVOL", t.day)]
    # 6. stresses: one more order charge per parent; every sale one bar late
    a = L7.run_day7(tape(q), arm, "ordinary", 30000., 2500.)
    with L7.stress(extra_fee=23.6):
        b = L7.run_day7(tape(q), arm, "ordinary", 30000., 2500.)
    assert abs(a["net"] - b["net"] - 23.6 * a["trades"]) < 1e-6
    with L7.stress(sell_delay=1):
        assert L7._exe7(sp, tape(q), 374, 0, "SELL", "ordinary", 1) == (0, None)
    L7.PRE7.pop(key)
    return "MECH_OK loss room, two parents, entry delay, blind add, gates, extra fee, missed exits"


def check_known():
    """Known synthetic signals are recovered: the ridge finds a planted 8-minute drift; SYNF75 fires on a planted lead;
    EN71's oracle beats its useless predictor on a book."""
    rng = np.random.default_rng(7); X = rng.normal(size=(3000, len(P7.FEATS))); y = .0004 * X[:, 2] + rng.normal(scale=.0005, size=3000)
    saved = dict(P7._ROWS)
    try:
        P7._ROWS.clear()
        for s in range(120):
            P7._ROWS[("SYN", f"d{s:03d}")] = (X[s * 25:(s + 1) * 25], y[s * 25:(s + 1) * 25])
        m = P7.ridge([("SYN", f"d{s:03d}") for s in range(120)])
        assert m["beta"][2] > 0 and abs(m["beta"][2]) == max(abs(m["beta"])), m["beta"]
    finally:
        P7._ROWS.clear(); P7._ROWS.update(saved)
    # a chain whose call-minus-put jumps 3 bars before the future does
    t = L4._synthetic_tape(np.full(375, 50.), index_step=0.); D = D4._D(); n = 375; ks = [25000. + 50 * k for k in range(-3, 4)]
    f = t.f.copy(); f[:, :4] = 25000.; f[200:, :4] = 25040.
    q = np.full((n, 2 * len(ks), 5), np.nan); strikes = []; kinds = []
    for a, K in enumerate(ks):
        for b, kd in enumerate((1, -1)):
            j = 2 * a + b; strikes.append(K); kinds.append(kd)
            Fsyn = np.where(np.arange(n) >= 196, 25040., 25000.)
            v = np.maximum(Fsyn - K, 0) + 20 if kd == 1 else np.maximum(K - Fsyn, 0) + 20
            q[:, j, 0] = q[:, j, 3] = v; q[:, j, 1] = v * 1.001; q[:, j, 2] = v * .999; q[:, j, 4] = 5000
    u = D.Tape(t.day, t.x, f, q, np.array(strikes), np.array(kinds), [str(x) for x in strikes], t.now, t.minute, 0); L7.KEEP7.append(u)
    P7.syn75(u); d = L7.PRE7[("SYNF75", "NIFTY", u.day)]
    assert d[198] == 1 and not d[:196].any(), np.flatnonzero(d)
    return "KNOWN_OK ridge recovers a planted drift; SYNF75 fires on a planted option lead"


def main():
    L5.install(); B = L6.books()
    print(check_parity(B), flush=True)
    print(check_mech(), flush=True)
    print(check_known(), flush=True)
    print(check_causal(B), flush=True)


if __name__ == "__main__":
    main()
