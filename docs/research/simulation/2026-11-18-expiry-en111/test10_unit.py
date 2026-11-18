"""Synthetic mechanics for every round-10 hook (run through test10.py unit). No historical money."""
from dataclasses import replace
from unittest.mock import patch
import math, unittest
import numpy as np
import round10  # noqa: F401
import test9_unit
from data8 import L7
import lab9, lab10, features10 as FX, families10 as FM, hmm10, learn10 as LN
L4, E = L7.L4, L7.E


def tape():
    t = test9_unit.tape(); t.state10 = {}; t.q10 = {}
    return t


def pos(j=10, entry_i=240, entry=15.05, runner=False, lots=1):
    return dict(direction=1, entry_i=entry_i, decision_i=entry_i - 1, open=lots, lots=lots, entry=entry, net=-30., reserve=1100., reserve0=1100.,
                runner=runner, j=j, peak=entry, stop=round(entry * .65, 2), dec_fut=100., dec_atr=2.)


class Activity114(unittest.TestCase):
    def setUp(self):
        self.t = tape(); F = self.t.f
        F[:, 3] = 100.
        for k in range(200, 240):
            F[k, 3] = 100. + (k % 2)                       # v0 = 1 (unit increments before the decision)
        self.sp = L4.spec_of(self.t)
        self.r = lab10.R10(L7.E03_ENV, hold=999, mg10="EN114", mgp10=(8., 12, "BASE_ONLY"))

    def test_exhaustion_after_minimum(self):
        t = self.t; F = t.f
        for k in range(240, 260):
            F[k, 3] = F[k - 1, 3] + 2.
        p = pos()
        self.assertEqual(lab10.hook114(self.sp, t, 243, p, self.r, 15., None, 1), (None, 1))        # age 3 < minimum 4
        self.assertEqual(lab10.hook114(self.sp, t, 244, p, self.r, 15., None, 1)[0], "ACTIVITY")
        self.assertAlmostEqual(p["_h114"]["v0"], 1.)

    def test_quiet_hits_the_wall_and_missing_falls_back(self):
        t = self.t; F = t.f; F[239:, 3] = F[239, 3]
        p = pos()
        self.assertEqual(lab10.hook114(self.sp, t, 251, p, self.r, 15., None, 1), (None, 1))
        self.assertEqual(lab10.hook114(self.sp, t, 252, p, self.r, 15., None, 1)[0], "WALL")
        F[243, 3] = np.nan; p = pos()
        self.assertEqual(lab10.hook114(self.sp, t, 247, p, self.r, 15., None, 1), (None, 1))
        self.assertEqual(lab10.hook114(self.sp, t, 248, p, self.r, 15., None, 1)[0], "TIME_FALLBACK")

    def test_scope_and_native_priority(self):
        t = self.t; F = t.f; F[239:, 3] = F[239, 3]
        p = pos(runner=True)
        self.assertEqual(lab10.hook114(self.sp, t, 260, p, self.r, 15., None, 1), (None, 1))
        r2 = replace(self.r, mgp10=(8., 12, "BASE_AND_RUNNER"))
        self.assertEqual(lab10.hook114(self.sp, t, 260, pos(runner=True), r2, 15., None, 1)[0], "WALL")
        self.assertEqual(lab10.hook114(self.sp, t, 260, pos(), self.r, 15., "STOP", 1), ("STOP", 1))

    def test_holdall_ends_runner(self):
        r = lab10.R10(L7.E03_ENV, hold=12, mg10="HOLDALL", mgp10=(12,))
        self.assertEqual(lab10.hook_holdall(self.sp, self.t, 252, pos(runner=True), r, 15., None, 1)[0], "WALL")
        self.assertEqual(lab10.hook_holdall(self.sp, self.t, 251, pos(runner=True), r, 15., None, 1), (None, 1))


class Fast113(unittest.TestCase):
    def setUp(self):
        self.t = tape(); self.sp = L4.spec_of(self.t); self.t.q10 = {"L3|p80": .01}

    def r(self, mode, stale=0):
        return lab10.R10(L7.E03_ENV, hold=12, mg10="EN113", mgp10=(3, "L3|p80", mode, stale))

    def test_deny_at_the_eight_minute_clock(self):
        D = {246: True, 247: True}
        with patch.object(lab10, "fast_D", lambda t, i, p, L, q: D.get(i, False)):
            p = pos()
            self.assertEqual(lab10.hook113(self.sp, self.t, 247, p, self.r("DENY"), 15., None, 1), (None, 1))     # age 7: no decision yet
            self.assertEqual(lab10.hook113(self.sp, self.t, 248, p, self.r("DENY"), 15., None, 1), (None, 1))     # 247&248: 248 False
        D = {247: True, 248: True}
        with patch.object(lab10, "fast_D", lambda t, i, p, L, q: D.get(i, False)):
            p = pos()
            self.assertEqual(lab10.hook113(self.sp, self.t, 248, p, self.r("DENY"), 15., None, 1)[0], "OI_DENY")
            p = pos(); p["_h113"] = {"c8": True}
            self.assertEqual(lab10.hook113(self.sp, self.t, 249, p, self.r("DENY"), 15., None, 1), (None, 1))     # one decision only

    def test_missing_reverts_to_native_eight(self):
        with patch.object(lab10, "fast_D", lambda *a: None):
            self.assertEqual(lab10.hook113(self.sp, self.t, 248, pos(), self.r("GIVEBACK"), 15., None, 1)[0], "TIME_MISSING")
            self.assertEqual(lab10.hook113(self.sp, self.t, 248, pos(), self.r("DENY"), 15., "STOP", 1), ("STOP", 1))

    def test_giveback_needs_confirmation_and_a_ten_percent_fall(self):
        t = self.t; t.q[241:244, 10, 3] = 20.; t.q[244, 10, 3] = 17.
        best = lab10.best_prev_bid(t, pos(), 244); self.assertEqual(best, E.down(20. - E.half(20.)))
        with patch.object(lab10, "fast_D", lambda *a: True):
            self.assertEqual(lab10.hook113(self.sp, t, 244, pos(), self.r("GIVEBACK"), 17.9, None, 1)[0], "OI_GIVEBACK")
            self.assertEqual(lab10.hook113(self.sp, t, 244, pos(), self.r("GIVEBACK"), 18.5, None, 1), (None, 1))
        with patch.object(lab10, "fast_D", lambda *a: False):
            self.assertEqual(lab10.hook113(self.sp, t, 244, pos(), self.r("GIVEBACK"), 17.9, None, 1), (None, 1))
        self.assertEqual(lab10.hook113(self.sp, t, 244, pos(), self.r("PRICE_ONLY"), 17.9, None, 1)[0], "PRICE_GIVEBACK")

    def test_fast_d_on_fixed_basket(self):
        t = self.t; p = pos(); i = 245
        pairs = lab9.fixed_pairs(t, p, lab10.REF)
        for c, q_ in pairs:
            t.oi8[i - 3, c] = 100.; t.oi8[i, c] = 120.; t.oi8[i - 3, q_] = 100.; t.oi8[i, q_] = 100.   # calls added: against a call
        self.assertTrue(lab10.fast_D(t, i, p, 3, .01))
        self.assertIsNone(lab10.fast_D(t, i, p, 3, math.nan))


class Wall125(unittest.TestCase):
    def test_wall_choice_and_ties(self):
        t = tape(); b = 240; c = float(t.close[b])
        ahead = sorted([j for j in range(len(t.strikes)) if t.kinds[j] == 1 and t.strikes[j] > c], key=lambda j: t.strikes[j])[:4]
        t.oi8[b, ahead] = [10., 50., 90., 20.]
        self.assertEqual(lab10.wall_of(t, b, 1), float(t.strikes[ahead[2]]))
        t.oi8[b, ahead] = [90., 50., 90., 20.]
        self.assertEqual(lab10.wall_of(t, b, 1), float(t.strikes[ahead[0]]))
        t.oi8[b, ahead[1:]] = np.nan
        self.assertIsNone(lab10.wall_of(t, b, 1))

    def test_exit_and_tighten(self):
        t = tape(); sp = L4.spec_of(t); b = 240; c = float(t.close[b])
        ahead = sorted([j for j in range(len(t.strikes)) if t.kinds[j] == 1 and t.strikes[j] > c], key=lambda j: t.strikes[j])[:4]
        t.oi8[b, ahead] = [10., 90., 20., 20.]; W = float(t.strikes[ahead[1]])
        r = lab10.R10(L7.E03_ENV, mg10="EN125", mgp10=("FROZEN_AT_ENTRY", "AT_WALL", "EXIT_ALL"))
        t.close[245] = W - 1
        self.assertEqual(lab10.hook125(sp, t, 245, pos(entry_i=b), r, 15., None, 1), (None, 1))
        t.close[246] = W
        p = pos(entry_i=b); lab10.hook125(sp, t, 245, p, r, 15., None, 1)
        self.assertEqual(lab10.hook125(sp, t, 246, p, r, 15., None, 1)[0], "OI_WALL")
        r2 = replace(r, mgp10=("FROZEN_AT_ENTRY", "HALF_STEP_BEFORE", "EXIT_ALL"))
        t.close[245] = W - 25
        self.assertEqual(lab10.hook125(sp, t, 245, pos(entry_i=b), r2, 15., None, 1)[0], "OI_WALL")
        r3 = replace(r, mgp10=("FROZEN_AT_ENTRY", "AT_WALL", "TIGHTEN"))
        p = pos(entry_i=b); p["peak"] = 30.
        self.assertEqual(lab10.hook125(sp, t, 246, p, r3, 15., None, 1), (None, 1)); self.assertEqual(p["stop"], 24.)
        self.assertEqual(lab10.hook125(sp, t, 247, p, r3, 15., "STOP", 1), ("STOP", 1))


class Range117(unittest.TestCase):
    def tape(self):
        t = tape(); F = t.f
        for k in range(150, 300):
            F[k, 3] = 100. + .5 * (k % 2)
        return t

    def test_event_first_per_side_and_separation(self):
        t = self.tape(); F = t.f; i = 262
        F[i - 1, 3] = 97.; F[i, 3] = 100.2
        F[i + 2, 3] = 103.; F[i + 3, 3] = 100.3                 # put rejection 3 bars later: inside the 5-minute separation
        F[i + 20, 3] = 97.; F[i + 21, 3] = 100.2                # second call rejection: first per side only
        ev = FX.range_events(t, .25)
        self.assertEqual([(e["i"], e["d"]) for e in ev], [(i, 1)])
        self.assertLess(ev[0]["er30"], .25)
        F[i - 1, 3] = 99.8                                       # not beyond the buffer
        self.assertNotIn(i, [e["i"] for e in FX.range_events(t, .25)])

    def test_levels_and_exits(self):
        ev = dict(d=1, lo=99., hi=101., q25=99.5, q75=100.5, A=2., i=0, F=100.)
        d, tg, st = FX.range_levels(ev, "MIDPOINT", .5); self.assertEqual((d, tg, st), (1, 100., 98.))
        self.assertEqual(FX.range_levels(ev, "OPPOSITE_QUARTILE", .25)[1:], (100.5, 98.5))
        t = tape(); sp = L4.spec_of(t); r = lab10.R10(L7.E03_ENV, mg10="EN117")
        p = pos(); p["range10"] = (1, 100.5, 98.)
        t.f[250, 3] = 97.9; self.assertEqual(lab10.hook117(sp, t, 250, p, r, 15., None, 1)[0], "RANGE_STRUCT")
        t.f[251, 3] = 100.5; self.assertEqual(lab10.hook117(sp, t, 251, p, r, 15., None, 1)[0], "RANGE_TARGET")
        t.f[252, 3] = 100.; self.assertEqual(lab10.hook117(sp, t, 252, p, r, 15., None, 1), (None, 1))
        self.assertEqual(lab10.hook117(sp, t, 250, p, r, 15., "STOP", 1), ("STOP", 1))


class Response115(unittest.TestCase):
    def tape(self):
        t = tape(); rng = np.random.default_rng(3)
        F = 100. + np.cumsum(rng.normal(0, 1, 375)); t.f[:, 3] = F
        for j in range(len(t.strikes)):
            slope = .5 if j == 10 else .1
            t.q[:, j, 3] = np.maximum(1., 15. + slope * (F - F[230]) * (1 if t.kinds[j] == 1 else -1))
        return t

    def test_fit_recovers_slope_and_ridge_shrinks(self):
        t = self.tape(); i = 260; P0 = t.q[i, 10, 3]; A = 2.
        a, b, mad, n = lab10.response_fit(t, i, 10, 40, 1e-9)
        self.assertAlmostEqual(b, .5 * A / P0, places=6); self.assertAlmostEqual(mad, 0., places=6); self.assertEqual(n, 37)
        b10 = lab10.response_fit(t, i, 10, 40, 10.)[1]; self.assertLess(abs(b10), abs(b))
        self.assertIsNone(lab10.response_fit(t, i, 10, 17, 1.))       # 14 endpoints < 15
        t.f[:, 3] = 100.; self.assertIsNone(lab10.response_fit(t, i, 10, 40, 1.))

    def test_pick_highest_score_and_fallback(self):
        t = self.tape(); sp = L4.spec_of(t); i = 260
        r = lab10.R10(L7.E03_ENV, chooser9="RESP", max_lots=1, admit9=False, resp10=(40, 1e-6, 0., "MODEL"))
        with patch.object(L4, "choose4", lambda *a: (2, 1, 15.)):
            pk = lab10.resp_pick(sp, t, i, 1, r, 2500., 30000.)
            self.assertEqual(pk[0], 10)
            t.f[:, 3] = 100.; note = []
            self.assertEqual(lab10.resp_pick(sp, t, i, 1, r, 2500., 30000., note), (2, 1, 15.)); self.assertEqual(note[0][0], "RESP_FALLBACK")

    def test_cost_gate(self):
        t = self.tape(); sp = L4.spec_of(t); i = 260
        far = dict(range10=(1, float(t.f[i, 3]) + 40., 0.)); near = dict(range10=(1, float(t.f[i, 3]) + .01, 0.))
        self.assertTrue(lab10.cost_gate(sp, t, i, 1, 10, far, 1.))
        self.assertFalse(lab10.cost_gate(sp, t, i, 1, 10, near, 2.))
        t.f[:, 3] = 100.; note = []
        self.assertFalse(lab10.cost_gate(sp, t, i, 1, 10, far, 1., note)); self.assertEqual(note[0][0], "GATE_NOFIT")


class DayLoop(unittest.TestCase):
    @staticmethod
    def _t(t, sig):
        t.sig9["K"] = sig; t.meta9["K"] = {}
        return t

    def run_(self, rule, sig, meta=None):
        t = tape(); t.sig9["K"] = sig; t.meta9["K"] = meta or {}
        return lab10.run_day10(t, replace(rule, sig9="K"), "ordinary", 30000., 2500., True)

    def test_profile_frozen_per_parent(self):
        sig = np.zeros(375, np.int8); sig[226] = 1; sig[262] = 1
        r = lab10.R10(L7.E03_ENV)
        out = self.run_(r, sig, {226: dict(prof10=(("hold", 12), ("target", 1.5)), tag10="ROOM")})
        p1, p2 = out["positions"]
        self.assertEqual(p1["r10"].hold, 12); self.assertEqual(p1["exit_i"] - p1["entry_i"], 13)   # TIME decided at age 12, filled next bar
        self.assertNotIn("r10", p2); self.assertEqual(p2["exit_i"] - p2["entry_i"], 9); self.assertEqual(p1["tag10"], "ROOM")

    def test_stress_is_scoped_to_the_run(self):
        sig = np.zeros(375, np.int8); sig[226] = 1; r = lab10.R10(L7.E03_ENV)
        base = self.run_(r, sig)["positions"][0]
        s = self.run_(replace(r, stress10=(("sell_delay", 1), ("extra_fee", 23.6))), sig)["positions"][0]
        t = tape(); i = s["events"][-1]["i"]; o = float(t.q[i + 1, s["j"], 0])
        self.assertEqual(i, base["events"][-1]["i"])                                     # decided on the same bar ...
        t.q[230:, :, 0] = 15. + .1 * np.arange(145)[:, None]
        s2 = lab10.run_day10(self._t(t, sig), replace(r, sig9="K", stress10=(("sell_delay", 1),)), "ordinary", 30000., 2500., True)["positions"][0]
        b2 = lab10.run_day10(self._t(t, sig), replace(r, sig9="K"), "ordinary", 30000., 2500., True)["positions"][0]
        j = s2["events"][-1]["i"]; nxt = float(t.q[j + 1, s2["j"], 0])
        self.assertEqual(s2["events"][-1]["price"], E.down(nxt - E.half(nxt)))           # ... executed at the next bar's price
        self.assertNotEqual(s2["events"][-1]["price"], b2["events"][-1]["price"])
        self.assertAlmostEqual(s["fees"] - base["fees"], 23.6, places=2)
        self.assertEqual(L7.PERT7["sell_delay"], 0); self.assertEqual(L7.PERT7["extra_fee"], 0.)
        d = self.run_(replace(r, entry_delay=1), sig)["positions"][0]
        self.assertEqual(d["entry_i"], base["entry_i"] + 1)

    def test_hooks_off_equals_round9(self):
        sig = np.zeros(375, np.int8); sig[226] = 1; sig[262] = -1
        t = tape(); t.sig9["K"] = sig; t.meta9["K"] = {}
        a = lab10.run_day10(t, lab10.R10(L7.E03_ENV, sig9="K"), "adverse", 30000., 2500., True)
        b = lab9.run_day9(t, lab9.R9(L7.E03_ENV, sig9="K"), "adverse", 30000., 2500., True)
        import score9
        self.assertEqual(score9.canon_day(a), score9.canon_day(b))


class States116(unittest.TestCase):
    def test_activation_rules(self):
        p = np.array([.5, .65, .7, .55, .3, .65, .61]); ok = np.ones(7, bool)
        self.assertEqual(hmm10.activate(p, ok, "IMMEDIATE").tolist(), [False, True, True, True, False, True, True])
        self.assertEqual(hmm10.activate(p, ok, "TWO_BAR_HYSTERESIS").tolist(), [False, False, True, True, False, False, True])
        ok2 = ok.copy(); ok2[1] = False
        self.assertEqual(hmm10.activate(p, ok2, "TWO_BAR_HYSTERESIS").tolist()[:3], [False, False, False])

    def test_fit_determinism_and_daily_reset(self):
        rng = np.random.default_rng(5); seqs = [np.column_stack([rng.random(90), rng.normal(size=90), rng.random(90) + .5]) for _ in range(40)]
        m1 = hmm10.fit(seqs, 2); m2 = hmm10.fit(seqs, 2)
        self.assertEqual(m1["hash"], m2["hash"])
        p, ok = hmm10.filter_day(m1, seqs[0]); p2, _ = hmm10.filter_day(m1, seqs[0])
        self.assertTrue(np.array_equal(p, p2)); self.assertTrue(np.allclose(p.sum(1), 1.))
        X = seqs[0].copy(); X[0] = np.nan
        p3, ok3 = hmm10.filter_day(m1, X); self.assertTrue(np.allclose(p3[0], m1["pi"])); self.assertFalse(ok3[0])

    def test_state_hook(self):
        t = tape(); sp = L4.spec_of(t); act = np.zeros(375, bool); act[248:250] = True; t.state10["S"] = act
        r = lab10.R10(L7.E03_ENV, hold=12, mg10="EN116", mgp10=("S",))
        p = pos(); p["net"] = -30.
        self.assertEqual(lab10.hook116(sp, t, 248, p, r, 20., None, 1), (None, 1))                    # active and in profit
        self.assertEqual(lab10.hook116(sp, t, 248, p, r, 15.05, None, 1)[0], "STATE_TIME")             # active, not in profit after fees
        self.assertEqual(lab10.hook116(sp, t, 250, p, r, 20., None, 1)[0], "STATE_TIME")               # inactive
        self.assertEqual(lab10.hook116(sp, t, 247, p, r, 1., None, 1), (None, 1))                      # before minute 8


def rows(n_dates, act="NEARER_150_12", net=500., funded=1, en87=True, setup="E03"):
    out = []
    for k in range(n_dates):
        lab = {a: dict(ordinary=(0., 0), adverse=(0., 0)) for a in LN.TREND} if setup == "E03" else {"RANGE": dict(ordinary=(0., 0), adverse=(0., 0))}
        lab[act] = dict(ordinary=(net, funded), adverse=(net, funded))
        out.append(dict(date=k, i=230, d=1, setup=setup, en87=en87, label=lab, dir8=1., levels=(1, 101., 99.) if setup == "RANGE" else None,
                        f=dict(er10=.3 + .01 * (k % 5), rank=.5, elapsed=.2, fric=.1, oiz=1., er_rank=.5, rvr=1.)))
    return out


class Learned(unittest.TestCase):
    def test_support_and_fallback(self):
        m = LN.Model118("RIDGE", "LIGHT", 0, "WITH_OI", rows(19), 120, 1)
        self.assertFalse(m.any_supported())
        ch, log = LN.policy118(m, rows(1)); self.assertEqual(ch[230][0], "LEGACY_100_8"); self.assertEqual(log[0][1], "FALLBACK_EN87")
        ch, log = LN.policy118(m, rows(1, en87=False)); self.assertEqual(ch, {}); self.assertEqual(log[0][1], "FALLBACK_CASH")
        m = LN.Model118("RIDGE", "LIGHT", 0, "WITH_OI", rows(30), 30, 1)
        self.assertFalse(m.any_supported())                                                           # < 40 training dates

    def test_positive_supported_action_is_chosen_and_negative_is_cash(self):
        m = LN.Model118("RIDGE", "HEAVY", 1, "WITH_OI", rows(30), 120, 1)
        self.assertTrue(m.supported["NEARER_150_12"]); self.assertFalse(m.supported["LEGACY_100_8"])
        ch, _ = LN.policy118(m, rows(1)); self.assertEqual(ch[230][0], "NEARER_150_12")
        m = LN.Model118("STUMP", "LIGHT", 0, "WITH_OI", rows(30, net=-500.), 120, 1)
        ch, log = LN.policy118(m, rows(1)); self.assertEqual(ch, {}); self.assertEqual(log[0][1], "CASH")

    def test_controller_tie_margin_and_fallback(self):
        tr = rows(30, act="LEGACY_100_8", net=500.) + rows(30, act="NEARER_150_12", net=500.)
        m = LN.Model120(1, tr, 120, 1)
        self.assertEqual(set(m.profs), {"EN87", "EN111"})
        ch, log = LN.policy120(m, rows(1), 0., {})
        self.assertEqual(log[0][1], "EN87")                                                          # exact tie -> EN87
        m2 = LN.Model120(1, rows(30, act="NEARER_150_12", net=600.) + rows(30, act="LEGACY_100_8", net=500.), 120, 1)
        st = {"current": "EN87"}; ch, log = LN.policy120(m2, rows(1), .25, st)
        self.assertEqual(log[0][1], "EN87")                                                          # within the margin: keep EN87
        st = {"current": "EN87"}; ch, log = LN.policy120(m2, rows(1), 0., st)
        self.assertEqual(log[0][1], "EN111"); self.assertEqual(st["current"], "EN111")
        m3 = LN.Model120(1, rows(10), 120, 1)
        ch, log = LN.policy120(m3, rows(1), 0., {}); self.assertEqual(log[0][1], "FALLBACK_EN87")

    def test_union(self):
        r = rows(1) + rows(1, setup="RANGE", en87=False, act="RANGE")
        r[1]["i"] = 240
        u = LN.union_policy(r); self.assertEqual(u[230][0], "NEARER_150_12"); self.assertEqual(u[240][0], "RANGE")


class Registry(unittest.TestCase):
    def test_counts_ids_needs(self):
        reg = FM.registry(); c = FM.counts(reg)
        self.assertEqual(c["cells"], 138 + 124 + 12 + 12)                # + 12 EN118 no-OI models + 12 EN112 phase-zero revision cells
        self.assertEqual(c["source_gated"], 12)
        for x in reg:
            if x.spec is None:
                continue
            uses_en87 = x.spec.arm == "EN87" or x.spec.build in ("EN112", "RND112", "EN116", "CALLGATE")
            if uses_en87:
                self.assertIn("OI", x.spec.needs, x.id)
        self.assertTrue(FM.sensex_ok(next(x for x in reg if x.id == "EN121:0001").spec))
        self.assertFalse(FM.sensex_ok(next(x for x in reg if x.id == "EN111:0001").spec))
