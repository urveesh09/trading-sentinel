"""SN170 - the online contextual bandit (PLAN.md). Each morning at 09:45 it picks one of six day-plays at Rs 15k
(wage Rs 1,500 / stop Rs 1,500 / one attempt unless said):
  0 none;
  1 RB30 follow: the first break of the first 30 minutes' range after 09:45, ATM;
  2 open fade: at 09:45 buy the ATM option against the move since the open;
  3 10:00 strangle: 1-OTM CE + 1-OTM PE held to 15:10 inside Rs 3,000 (skipped above Rs 15k);
  4 RB30 follow with the 2-OTM option;
  5 VWAP reversion: at 09:45, when the index is >= 2 ATR from VWAP, buy toward VWAP.
Context (causal at 09:45, standardised online): gap, yesterday's ADX, VIX ratio, OR30 width % of the index, R_today.
Thompson sampling on a Bayesian linear model per arm (prior precision 1, noise from the arm's residuals), reward =
net / 1,000; learns every day from 2023; 20 seeds. Scored online on development (2023 shown, 2024 - 2026 dev the
judge) against every fixed play, the best fixed play by leave-one-year-out and a random play. SN181 continues it on
TEST from its development state."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pw  # noqa: E402

C = pw.C
ARMS = ("none", "RB30 follow", "open fade", "10:00 strangle", "RB30 OTM2", "VWAP reversion")
I945, I1000 = 30, 45
WALLET, WAGE = 15000.0, 1500.0


def once(i, opt, strike):
    done = [False]

    def pick(S, i0, realized):
        if done[0] or i < i0:
            return None
        done[0] = True
        return i, opt, strike
    return pick


def play_nets(S):
    c, o, vw, atr = S.F["c"], S.F["o"], S.F["vwap"], S.F["atr"]
    out = [0.0]
    for off in (0,):
        out.append(pw.play(S, pw.range_break_picker(30, off), WALLET, WAGE, 1500.0, 1, day_limit=3000.0)[0])
    d = -1 if c[I945] > o[0] else 1
    out.append(pw.play(S, once(I945, "CE" if d > 0 else "PE", pw.atm(S, I945)), WALLET, WAGE, 1500.0, 1, day_limit=3000.0)[0])
    K = pw.atm(S, I1000)
    got = pw.pb.struct_path(S, I1000, [(K + pw.STEP, "CE"), (K - pw.STEP, "PE")])
    out.append(pw.pb.net(got, i=I1000, room=3000.0, ceiling=WALLET, n_legs=2))
    out.append(pw.play(S, pw.range_break_picker(30, 2), WALLET, WAGE, 1500.0, 1, day_limit=3000.0)[0])
    gapv = c[I945] - vw[I945]
    if abs(gapv) >= 2 * atr[I945]:
        d = -1 if gapv > 0 else 1
        out.append(pw.play(S, once(I945, "CE" if d > 0 else "PE", pw.atm(S, I945)), WALLET, WAGE, 1500.0, 1, day_limit=3000.0)[0])
    else:
        out.append(0.0)
    return out


def context(S):
    c, h, l = S.F["c"], S.F["h"], S.F["l"]
    adx = C.adx(S.day)
    vl, vm = C.vix_prev(S.day)
    rt = C.r_today(S, I945)
    return np.array([1.0, S.F["gap"] * 100, (adx if adx is not None else 25.0) / 25.0,
                     (vl / vm) if vl else 1.0, (float(np.max(h[:I945 + 1])) - float(np.min(l[:I945 + 1]))) / c[I945] * 100,
                     rt if rt is not None else 1.0])


class Bandit:
    def __init__(self, n_arms, dim, seed):
        self.A = [np.eye(dim) for _ in range(n_arms)]
        self.b = [np.zeros(dim) for _ in range(n_arms)]
        self.res = [[] for _ in range(n_arms)]
        self.rng = np.random.default_rng(seed)
        self.mu, self.m2, self.n = np.zeros(dim), np.zeros(dim), 0

    def _z(self, x):
        sd = np.sqrt(self.m2 / max(1, self.n - 1)) if self.n > 1 else np.ones_like(x)
        z = (x - self.mu) / np.where(sd > 0, sd, 1.0)
        z[0] = 1.0
        return np.clip(z, -5, 5)

    def choose(self, x):
        z = self._z(x)
        scores = []
        for a in range(len(self.A)):
            cov = np.linalg.inv(self.A[a])
            s2 = float(np.var(self.res[a])) if len(self.res[a]) > 5 else 1.0
            w = self.rng.multivariate_normal(cov @ self.b[a], s2 * cov)
            scores.append(float(z @ w))
        return int(np.argmax(scores)), z

    def learn(self, x, z, rewards_all, arm):
        r = rewards_all[arm]
        self.A[arm] += np.outer(z, z)
        self.b[arm] += r * z
        pred = float(z @ (np.linalg.inv(self.A[arm]) @ self.b[arm]))
        self.res[arm].append(r - pred)
        self.n += 1
        dlt = x - self.mu
        self.mu += dlt / self.n
        self.m2 += dlt * (x - self.mu)


def run_bandit(days, ctx, nets, seed):
    """Online: choose with today's context, then learn only the chosen arm's reward. Returns chosen arms."""
    bd = Bandit(len(ARMS), len(ctx[days[0]]), seed)
    chosen = []
    for d in days:
        a, z = bd.choose(ctx[d])
        chosen.append(a)
        bd.learn(ctx[d], z, np.array(nets[d]) / 1000.0, a)
    return chosen, bd


if __name__ == "__main__":
    out_path = HERE / "results-sn170.json"
    if out_path.exists():
        raise SystemExit("SN170 is scored once")
    ss = pw.dev_sessions()
    days = [S.day for S in ss]
    nets = {S.day: play_nets(S) for S in ss}
    ctx = {S.day: context(S) for S in ss}
    years = ("2023", "2024", "2025", "2026")
    res = {"fixed": {}}
    for a, name in enumerate(ARMS):
        res["fixed"][name] = {y: round(sum(nets[d][a] for d in days if d[:4] == y)) for y in years}
    loyo = {}
    for y in years:
        pick = max(range(len(ARMS)), key=lambda a: sum(nets[d][a] for d in days if d[:4] != y))
        loyo[y] = {"arm": ARMS[pick], "net": round(sum(nets[d][pick] for d in days if d[:4] == y))}
    res["loyo_best_fixed"] = loyo
    seeds = []
    for seed in range(20):
        ch, _bd = run_bandit(days, ctx, nets, 1700 + seed)
        dn = {d: nets[d][a] for d, a in zip(days, ch) if a != 0 and nets[d][a] != 0}
        seeds.append({"by_year": {y: round(sum(v for d, v in dn.items() if d[:4] == y)) for y in years},
                      "arm_share_2026": [round(float(np.mean([a == k for d, a in zip(days, ch) if d[:4] == "2026"])), 3)
                                         for k in range(len(ARMS))],
                      "wage_share": pw.wage_stats(dn, days, WALLET, WAGE)["wage_share"]})
    judge = [sum(s["by_year"][y] for y in ("2024", "2025", "2026")) for s in seeds]
    rng = np.random.default_rng(170)
    rnd = [sum(nets[d][int(rng.integers(0, len(ARMS)))] for d in days if d[:4] in ("2024", "2025", "2026")) for _ in range(200)]
    res["bandit"] = {"seeds": seeds, "judge_2024_2026_mean": round(float(np.mean(judge))),
                     "judge_min": round(float(np.min(judge))), "judge_max": round(float(np.max(judge)))}
    res["random_play_2024_2026"] = {"mean": round(float(np.mean(rnd))), "p95": round(float(np.percentile(rnd, 95)))}
    res["loyo_fixed_2024_2026"] = sum(loyo[y]["net"] for y in ("2024", "2025", "2026"))
    res["dev_pass"] = bool(res["bandit"]["judge_2024_2026_mean"] > 0 and res["bandit"]["judge_2024_2026_mean"] > res["random_play_2024_2026"]["p95"]
                           and res["bandit"]["judge_2024_2026_mean"] > res["loyo_fixed_2024_2026"])
    print("SN170", json.dumps({k: v for k, v in res.items() if k != "bandit"}), "\nbandit", json.dumps({k: v for k, v in res["bandit"].items() if k != "seeds"}), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
