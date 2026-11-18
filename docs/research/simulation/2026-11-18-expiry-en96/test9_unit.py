"""Synthetic mechanics for every round-9 hook (run through test9.py unit). No historical money."""
from dataclasses import replace
from unittest.mock import patch
import math, unittest
import numpy as np
import round8  # noqa: F401
import lab8
import test8
import signals9 as S9, lab9, families9 as F
L7 = lab8.L7; L4 = L7.L4; E = L7.E


def tape():
    t = test8.synthetic(); t.sig9, t.meta9, t.logs9 = {}, {}, {}; t.q9 = {"REF": .01}
    t.features[10] = t.features[10].copy(); t.features[10][:, 4] = 2.
    t.f = t.f.astype(float).copy(); t.f[:, :] = 100.
    return t


class Information(unittest.TestCase):
    def test_zero_is_valid_missing_is_not(self):
        t = tape(); i = 230; pairs = S9.strict_pairs(t, i, 2)
        for c, p in pairs:
            t.oi8[i - 15, c] = 0.; t.oi8[i, c] = 0.; t.oi8[i - 15, p] = 100.; t.oi8[i, p] = 120.
        v = S9.rep_score(t, i, (15, 1, "CURRENT_ATM", "POOLED"))
        self.assertAlmostEqual(v, .2)
        for c, p in pairs:
            t.oi8[i, c] = np.nan
        self.assertTrue(math.isnan(S9.rep_score(t, i, (15, 1, "CURRENT_ATM", "POOLED"))))

    def test_strict_basket_and_jackknife(self):
        t = tape(); i = 230
        self.assertIsNone(S9.strict_pairs(t, i, 6))                 # catalogue has +-4 strikes only
        pairs = S9.strict_pairs(t, i, 3); self.assertEqual(len(pairs), 7)
        for n, (c, p) in enumerate(pairs):
            t.oi8[i - 15, c] = 100.; t.oi8[i, c] = 100. - (50 if n == 0 else 0); t.oi8[i - 15, p] = 100.; t.oi8[i, p] = 100.
        pooled = S9.rep_score(t, i, (15, 3, "CURRENT_ATM", "POOLED")); jack = S9.rep_score(t, i, (15, 3, "CURRENT_ATM", "MEDIAN_LEAVE_ONE_PAIR_OUT"))
        self.assertAlmostEqual(pooled, 50 / 1400); self.assertAlmostEqual(jack, 50 / 1200)   # one strike drives it: median of LOO keeps it
        for c, p in pairs[1:]:
            t.oi8[i, c] = np.nan
        self.assertTrue(math.isnan(S9.rep_score(t, i, (15, 3, "CURRENT_ATM", "MEDIAN_LEAVE_ONE_PAIR_OUT"))))

    def test_frozen_anchor(self):
        t = tape(); k = int(np.searchsorted(t.minute, 780))
        self.assertEqual(S9.anchor_of(t, k - 1, "FROZEN_1300_ATM"), -1); self.assertEqual(S9.anchor_of(t, k + 30, "FROZEN_1300_ATM"), k)
        self.assertEqual(S9.anchor_of(t, k + 30, "LAG15_ATM"), k + 15)

    def test_threshold_prior_only(self):
        th = S9.Threshold(20, 80); t = tape()
        for n in range(19):
            th.hist.append(np.full(90, float(n)))
        self.assertTrue(math.isnan(th.value()))
        th.hist.append(np.full(90, 19.)); self.assertTrue(np.isfinite(th.value()))
        th2 = S9.Threshold(20, 80); th2.hist = [np.full(5, 1.)] * 20; self.assertTrue(math.isnan(th2.value()))   # < 200 observations

    def test_gate_veto_tilt_grade(self):
        e = np.array([1, -1, 1, 1, 0], np.int8); S = np.array([.5, .5, np.nan, -.5, 9]); w = np.ones(5, bool)
        self.assertEqual(S9.gate(e, S, .1, w).tolist(), [1, 0, 0, 0, 0])
        self.assertEqual(S9.gate(e, S, .1, w, "VETO").tolist(), [1, 0, 1, 0, 0])
        out, caps = S9.tilt_caps(e, S, .1, w); self.assertEqual(out.tolist(), [1, -1, 1, 1, 0]); self.assertEqual(sorted(caps), [1, 2, 3])
        S2 = np.array([.05, .15, .25, -.01, 0]); e2 = np.array([1, 1, 1, 1, 0], np.int8)
        out, caps = S9.graded_caps(e2, S2, .1, w, 1, 2, 2.)
        self.assertEqual(out.tolist(), [1, 1, 1, 0, 0]); self.assertEqual([caps[i]["max_lots"] for i in (0, 1, 2)], [1, 2, 3])


class Arms(unittest.TestCase):
    def setUp(self):
        self.t = tape(); self.S = np.full(375, .5); self.q = .1
        self.pick = patch.object(L4, "choose4", lambda *a: (0, 1, 20.))
        self.pick.start()

    def tearDown(self):
        self.pick.stop()

    def test_confirm_one_active_arm_and_ceiling(self):
        t = self.t; i = 230; ev = np.zeros(375, np.int8); ev[i] = 1; ev[i + 1] = 1
        t.f[i + 2:, 3] = 101.
        out, picks, logs = S9.arms99(t, ev, self.S, self.q, "CONFIRM", 3, .25, 1.08, L7.E03_ENV)
        self.assertEqual(np.flatnonzero(out).tolist(), [i + 2]); self.assertEqual(picks[i + 2]["event_i"], i)
        self.assertEqual(logs[1]["status"], "ARM_ACTIVE")
        t.q[i + 1:, 0, 3] = 20.                                     # ask above 1.08 x event ask: never qualifies
        out, _, logs = S9.arms99(t, ev[:].copy(), self.S, self.q, "CONFIRM", 3, .25, 1.08, L7.E03_ENV)
        self.assertFalse(out.any()); self.assertEqual(logs[0]["status"], "TTL_EXPIRED")

    def test_information_lost_and_missing_disarm(self):
        t = self.t; i = 230; ev = np.zeros(375, np.int8); ev[i] = 1; t.f[i + 2:, 3] = 101.
        S = self.S.copy(); S[i + 1] = .05
        _, _, logs = S9.arms99(t, ev, S, self.q, "CONFIRM", 3, .25, 1.08, L7.E03_ENV); self.assertEqual(logs[0]["status"], "INFORMATION_LOST")
        S = self.S.copy(); S[i + 1] = np.nan
        _, _, logs = S9.arms99(t, ev, S, self.q, "CONFIRM", 3, .25, 1.08, L7.E03_ENV); self.assertEqual(logs[0]["status"], "INFORMATION_LOST")

    def test_reclaim(self):
        t = self.t; i = 230; ev = np.zeros(375, np.int8); ev[i] = 1
        t.f[i + 1, 3] = 101.; t.f[i + 2, 3] = 100.; t.f[i + 2, 1] = 100.2; t.f[i + 3, 3] = 100.5
        out, _, _ = S9.arms99(t, ev, self.S, self.q, "RECLAIM", 5, .5, 1.08, L7.E03_ENV)
        self.assertEqual(np.flatnonzero(out).tolist(), [i + 3])

    def test_en104_priority_opposite_and_structure(self):
        t = self.t; i = 230; e = np.zeros(375, np.int8); e[i] = 1; S = np.full(375, .05); S[i + 2] = .5
        out, picks, logs = S9.arms104(t, e, S, .1, .1, 3, "STRUCTURE_HOLDS", L7.E03_ENV)
        self.assertEqual(np.flatnonzero(out).tolist(), [i + 2])
        e2 = e.copy(); e2[i + 1] = -1
        out, _, logs = S9.arms104(t, e2, S, .1, .1, 3, "STRUCTURE_HOLDS", L7.E03_ENV); self.assertEqual(logs[0]["status"], "OPPOSITE_E03")
        e3 = e.copy(); e3[i + 1] = 1; S3 = S.copy(); S3[i + 1] = .5           # an immediate EN87 event wins and cancels the arm
        out, _, logs = S9.arms104(t, e3, S3, .1, .1, 3, "STRUCTURE_HOLDS", L7.E03_ENV)
        self.assertEqual(logs[0]["status"], "IMMEDIATE_PRIORITY"); self.assertEqual(np.flatnonzero(out).tolist(), [i + 1])
        t.f[i + 1, 3] = 50.                                                 # close beyond the 3-bar adverse extreme
        _, _, logs = S9.arms104(t, e, S, .1, .1, 3, "STRUCTURE_HOLDS", L7.E03_ENV); self.assertEqual(logs[0]["status"], "STRUCTURE_BROKEN")
        out, _, _ = S9.arms104(t, e, np.full(375, .0), .1, .1, 3, "NONE", L7.E03_ENV, unconditional=True)
        self.assertEqual(np.flatnonzero(out).tolist(), [i + 3])


class Contracts(unittest.TestCase):
    def test_admission_and_rankings(self):
        t = tape(); sp = L4.spec_of(t); i = 230; r = lab9.R9(L7.E03_ENV, max_lots=1, chooser9="NEAREST", admit9=True)
        with patch.object(L4, "choose4", lambda *a: None):
            self.assertIsNone(lab9.contract_pick(sp, t, i, 1, r, 2500., 30000.))
            self.assertIsNotNone(lab9.contract_pick(sp, t, i, 1, replace(r, admit9=False), 2500., 30000.))
        pick = lab9.contract_pick(sp, t, i, 1, replace(r, admit9=False), 2500., 30000.)
        dist = [abs(float(t.strikes[j]) - float(t.close[i])) for j in range(len(t.strikes)) if t.kinds[j] == 1]
        self.assertEqual(abs(float(t.strikes[pick[0]]) - float(t.close[i])), min(dist))
        t.q[i, :, 3] = np.where(t.kinds == 1, 15., 15.); t.q[i, 2, 3] = 30.
        cs = lab9.candidates(sp, t, i, 1, r, 2500., 30000.); self.assertTrue(all(c["fric"] > 0 for c in cs))
        lo = min(cs, key=lambda c: (c["fric"], c["dist"], c["K"], c["j"]))
        self.assertEqual(lab9.contract_pick(sp, t, i, 1, replace(r, admit9=False, chooser9="MINFRIC"), 2500., 30000.)[0], lo["j"])
        self.assertIsNone(lab9.contract_pick(sp, t, i, 1, replace(r, admit9=False, fric9=1e-6), 2500., 30000.))

    def test_staged_plan_reserves_the_add(self):
        t = tape(); sp = L4.spec_of(t); i = 230; r = lab9.R9(L7.E03_ENV, stage9=.5, gain9=.1, oiadd9="STILL_QUALIFIED")
        ask = L4.ask_of(t.q[i, 0, 3]); lim = E.down(ask * 1.08)
        N, n1, n2, a0 = lab9.staged_plan(sp, t, i, 0, 3, lim, r, 2500., 30000.)
        self.assertEqual(N, n1 + n2); self.assertLessEqual(L4.reserve(sp, lim, n1) + (L4.reserve(sp, E.down(1.4 * a0), n2) if n2 else 0), 2500.01)
        self.assertEqual(lab9.staged_plan(sp, t, i, 0, 3, lim, replace(r, stage9=1 / 3), 2500., 30000.)[:3], (N, n1, n2))   # same split <= 3 lots
        self.assertEqual(lab9.staged_plan(sp, t, i, 0, 1, lim, r, 2500., 30000.)[:3], (1, 1, 0))                          # impossible split
        self.assertEqual(lab9.staged_plan(sp, t, i, 0, 3, lim, replace(r, stage9=-1.), 2500., 30000.)[1:3], (N, 0))


class Management(unittest.TestCase):
    def pos(self, t):
        return dict(direction=1, entry_i=230, open=2, lots=2, entry=10., net=-40., reserve=1400., reserve0=1400., dec_fut=100., dec_atr=2.,
                    runner=False, j=0)

    def test_extension_activation_failures_cap_runner(self):
        t = tape(); sp = L4.spec_of(t); r = lab9.R9(L7.E03_ENV, ext9="PRICE", extcap9=16, extact9=0.)
        p = self.pos(t)
        with patch.object(lab9, "price_ok", lambda *a: True):
            self.assertEqual(lab9.extension9(sp, t, 238, p, r, 12., "TIME", 2), (None, 2))
        with patch.object(lab9, "price_ok", lambda *a: False):
            self.assertEqual(lab9.extension9(sp, t, 239, p, r, 12., "TIME", 2)[0], None)
            self.assertEqual(lab9.extension9(sp, t, 240, p, r, 12., "TIME", 2)[0], "EXT_FAIL")
        p = self.pos(t); p["_ext9"] = dict(fails=0)
        with patch.object(lab9, "price_ok", lambda *a: None):
            self.assertEqual(lab9.extension9(sp, t, 239, p, r, 12., "TIME", 2)[0], "EXT_MISSING")
        p = self.pos(t); p["_ext9"] = dict(fails=0)
        self.assertEqual(lab9.extension9(sp, t, 246, p, r, 12., "TIME", 2)[0], "TIME_CAP")
        self.assertEqual(lab9.extension9(sp, t, 240, p, r, 12., "STOP", 2)[0], "STOP")
        p = self.pos(t); p["runner"] = True
        self.assertEqual(lab9.extension9(sp, t, 238, p, r, 12., None, 1), (None, 1))
        p = self.pos(t)                                                             # loss at minute 8: no extension
        self.assertEqual(lab9.extension9(sp, t, 238, p, r, 9., "TIME", 2)[0], "TIME")

    def test_damage_consecutive_and_reset(self):
        t = tape(); sp = L4.spec_of(t); r = lab9.R9(L7.E03_ENV, dmg9="ENTRY", dmgk9=0., dmgn9=2)
        p = self.pos(t); t.f[:, 3] = 98.
        with patch.object(lab9, "fixed_score", side_effect=[-1., np.nan, -1., -1.]):
            self.assertIsNone(lab9.damage9(sp, t, 240, p, r)); self.assertIsNone(lab9.damage9(sp, t, 241, p, r))
            self.assertIsNone(lab9.damage9(sp, t, 242, p, r)); self.assertEqual(lab9.damage9(sp, t, 243, p, r), "DAMAGE9")

    def test_native_exit_has_priority(self):
        t = tape(); sp = L4.spec_of(t); r = lab9.R9(L7.E03_ENV, dmg9="NONE", dmgk9=0., dmgn9=1)
        with patch.object(lab8, "decide8", lambda *a: ("STOP", 2)), patch.object(lab9, "damage9", side_effect=AssertionError):
            self.assertEqual(lab9.decide9(sp, t, 240, self.pos(t), r, 9., None), ("STOP", 2))


class DayLoop(unittest.TestCase):
    def test_stage_add_uses_a_submission_and_fits_the_episode(self):
        t = tape(); i = 230; sig = np.zeros(375, np.int8); sig[i] = 1; sig[i + 40] = 1
        t.sig9["k"] = sig; t.meta9["k"] = {}
        t.q[:, :, :4] = 8.; t.q[i + 3:i + 30, :, :4] = 9.6                           # cheap enough for a 3-lot plan; bid gain > 10%
        r = lab9.R9(L7.E03_ENV, sig9="k", stage9=.5, gain9=.1, oiadd9="STILL_QUALIFIED")
        with patch.object(lab9, "fixed_score", lambda *a: 1.), patch.object(L4, "_avail", lambda *a: True):
            out = lab9.run_day9(t, r, "ordinary", 30000., 2500., True)
        p = out["positions"][0]
        self.assertEqual((p["planned9"], p["stage_added"]), (3, 2))
        self.assertEqual(out["intents"], 2); self.assertEqual(out["trades"], 1)           # the add consumed the second buy
        self.assertLessEqual(p["reserve"], p["room"] + .02)

    def test_wallet_steps_constant_rule(self):
        t = tape(); sig = np.zeros(375, np.int8); sig[230] = 1; t.sig9["k"] = sig; t.meta9["k"] = {}
        r = lab9.R9(L7.E03_ENV, sig9="k")
        with patch.object(L4, "_avail", lambda *a: True):
            a = lab9.wallet9([t, t, t], r); b = lab9.wallet_steps([(t, r)] * 3)
        self.assertEqual(a["days"], b["days"])
        self.assertEqual(lab9.scale_of(4000), 0.); self.assertEqual(lab9.scale_of(3999), .25); self.assertEqual(lab9.scale_of(1499), 1.)


class Registry(unittest.TestCase):
    def test_counts_ids_and_expansion(self):
        reg = F.registry(); c = F.counts(reg)
        self.assertEqual(c["cells"], 318); self.assertEqual(c["packet"], 12)
        self.assertEqual(c["by_family"]["EN105"], 64)
        self.assertEqual(sum(v for k, v in c["by_family"].items() if int(k[2:]) <= 105), 231)
        self.assertEqual(sum(v for k, v in c["by_family"].items() if int(k[2:]) > 105), 87)
        self.assertEqual(len({x.id for x in reg}), len(reg))
        again = F.registry(); self.assertEqual([x.id for x in reg], [x.id for x in again])
        self.assertTrue(all(not x.spec.needs_oi() for x in reg if x.id in ("REF:E03_env", "REF:E032_native", "REF:EN55_native")))


if __name__ == "__main__":
    unittest.main()
