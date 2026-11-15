"""SN181 - the frozen TEST (PLAN.md). The latest 5% of sessions (2026-08-20 ... 2026-10-28, 37 sessions), scored once.
Every candidate as frozen by its development script (saved final models / thresholds / variants); nothing is chosen
here. The pass rule (PLAN.md): TEST net > 0 and above the matched null's 95th percentile; wage share above the null's
mean; net > 0 at Rs 400 per lot and one minute late; net without the best 2 days > 0; passed development.
Today's system (Gold v5) and the coin-flip wage trader are scored for reference."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import p3  # noqa: E402
import p4  # noqa: E402
import pml  # noqa: E402
import pw  # noqa: E402
import sn166  # noqa: E402
import sn168  # noqa: E402
import sn170  # noqa: E402
import sn172  # noqa: E402
import sn173  # noqa: E402
import sn174  # noqa: E402
import sn176  # noqa: E402

C = pw.C
L = pw.L
LOCAL = HERE / "_local"


def res_of(name):
    return json.loads((HERE / f"results-{name}.json").read_text(encoding="utf-8"))


def load(name):
    return pickle.loads((LOCAL / name).read_bytes())


def verdict(dn, days, wallet, null_p95, null_wage, net400, late1, dev_pass):
    s = pw.wage_stats(dn, days, wallet)
    xs = sorted(dn.values(), reverse=True)
    out = {"net": s["net"], "trade_days": s["trade_days"], "wage_days": s["wage_days"], "wage_share": s["wage_share"],
           "red_days": s["red_days"], "null_p95": null_p95, "null_wage_share": null_wage,
           "net_400": None if net400 is None else round(net400), "late_1": None if late1 is None else round(late1),
           "without_best_2": round(sum(xs[2:])), "dev_pass": bool(dev_pass)}
    out["PASS"] = bool(s["net"] > 0 and null_p95 is not None and s["net"] > null_p95 and s["wage_share"] > (null_wage or 0)
                       and (net400 or 0) > 0 and (late1 or 0) > 0 and sum(xs[2:]) > 0 and dev_pass)
    return out


def random_day_null(pool, k, wallet, days, draws=2000, seed=181):
    rng = np.random.default_rng(seed)
    nets, shares = [], []
    items = list(pool.items())
    for _ in range(draws):
        if not items or not k:
            nets.append(0.0)
            shares.append(0.0)
            continue
        pick = rng.choice(len(items), min(k, len(items)), replace=False)
        dn = {items[i][0]: items[i][1] for i in pick}
        st = pw.wage_stats(dn, days, wallet)
        nets.append(st["net"])
        shares.append(st["wage_share"])
    return round(float(np.percentile(nets, 95))), round(float(np.mean(shares)), 4), round(float(np.mean(nets)))


if __name__ == "__main__":
    out_path = HERE / "results-sn181.json"
    if out_path.exists():
        raise SystemExit("SN181 is scored once")
    TEST = pw.test_sessions()
    tdays = [S.day for S in TEST]
    res = {"test": {"from": tdays[0], "to": tdays[-1], "sessions": len(tdays)}, "reference": {}, "candidates": {}}

    # --- reference: today's system and the coin-flip wage trader
    for key in ("Rs 15k", "Rs 30k growing (production)"):
        g = p4.gold(key, keep=pw.is_test)
        res["reference"][f"Gold v5 {key}"] = pw.wage_stats(g, tdays, p4.WALLETS[key][1])
    coin = []
    for k in range(200):
        dn = {}
        for S in TEST:
            n, tr = pw.play(S, pw.random_picker(pw.seed_of(S.day, k)), 15000.0, 1500.0, 1500.0, 1, day_limit=3000.0)
            if tr:
                dn[S.day] = n
        coin.append(pw.wage_stats(dn, tdays, 15000.0))
    res["reference"]["coin-flip wage trader (SN163 main cell)"] = {
        "net_mean": round(float(np.mean([s["net"] for s in coin]))), "net_p5": round(float(np.percentile([s["net"] for s in coin], 5))),
        "net_p95": round(float(np.percentile([s["net"] for s in coin], 95))),
        "wage_share_mean": round(float(np.mean([s["wage_share"] for s in coin])), 4)}
    print("SN181 reference", json.dumps(res["reference"], default=float)[:1500], flush=True)

    # --- SN164 range break (ATM)
    def rb(stress=pw.STRESS, late=0):
        dn = {}
        for S in TEST:
            n, tr = pw.play(S, pw.range_break_picker(15, 0), 15000.0, 1500.0, 1500.0, 1, day_limit=3000.0, stress=stress, late=late)
            if tr:
                dn[S.day] = n
        return dn
    dn = rb()
    sess = {S.day: S for S in TEST}
    rng = np.random.default_rng(1641)
    nulls = []
    for _ in range(500):
        x = {}
        for d in dn:
            n, tr = pw.play(sess[d], pw.random_picker(int(rng.integers(1 << 30))), 15000.0, 1500.0, 1500.0, 1, day_limit=3000.0)
            if tr:
                x[d] = n
        nulls.append(pw.wage_stats(x, tdays, 15000.0))
    res["candidates"]["SN164 range break ATM"] = verdict(dn, tdays, 15000.0, round(float(np.percentile([s["net"] for s in nulls], 95))),
                                                         round(float(np.mean([s["wage_share"] for s in nulls])), 4),
                                                         sum(rb(400.0).values()), sum(rb(late=1).values()), False)

    # --- SN167 the wage classifier
    bar = sn166.build()
    tidx = [s for s, d in enumerate(bar["days"]) if d >= pw.TEST_FROM]
    t167 = load("sn167_test.pkl")
    dn, _n = pml.policy(t167["P_test"], bar, tidx, t167["theta"])
    taken = pml.trades_per_day(t167["P_test"], bar, tidx, t167["theta"])
    nl = pml.null_summary(pml.matched_null(bar, taken), tdays) if taken else {"net_p95": 0, "wage_share_mean": 0}
    res["candidates"]["SN167 wage classifier"] = verdict(dn, tdays, 15000.0, nl["net_p95"], nl["wage_share_mean"], None, None,
                                                         res_of("sn167")["dev_pass_ml_analog"])

    # --- SN168 meta-labelled signals
    t168 = load("sn168_test.pkl")
    dn, _n, _o, taken = sn168.gated_policy(t168["E"], t168["P_test"], bar, t168["theta"], tidx)
    nl = pml.null_summary(pml.matched_null(bar, taken), tdays) if taken else {"net_p95": 0, "wage_share_mean": 0}
    res["candidates"]["SN168 meta-labelled signals"] = verdict(dn, tdays, 15000.0, nl["net_p95"], nl["wage_share_mean"], None, None,
                                                               res_of("sn168")["dev_pass_ml_analog"])

    # --- SN169 learned exit (per entry, against the barrier-only exit)
    t169 = load("sn169_test.pkl")
    P, xnet, phi = t169["P_test"], t169["extra_net"], t169["phi"]

    def ex(e, use):
        if use:
            for t in range(e["first_state"], e["first_state"] + e["n_states"]):
                if P[t] == P[t] and P[t] < phi:
                    return float(xnet[t])
        return float(e["exit_net"])
    row = {}
    for kind in ("random", "signal"):
        te = [e for e in t169["entries"] if bar["days"][e["s"]] >= pw.TEST_FROM and e["kind"] == kind]
        row[kind] = {"entries": len(te), "barriers only": round(sum(ex(e, False) for e in te)), "learned exit": round(sum(ex(e, True) for e in te))}
    row["dev_profitable"] = res_of("sn169")["dev_profitable"]
    res["candidates"]["SN169 learned exit"] = row

    # --- SN170 the bandit, online through development into TEST
    allS = pw.sessions()
    nets = {S.day: sn170.play_nets(S) for S in allS}
    ctx = {S.day: sn170.context(S) for S in allS}
    days_all = [S.day for S in allS]
    seeds = []
    for seed in range(20):
        ch, _b = sn170.run_bandit(days_all, ctx, nets, 1700 + seed)
        seeds.append(sum(nets[d][a] for d, a in zip(days_all, ch) if d >= pw.TEST_FROM))
    rng = np.random.default_rng(1701)
    rnd = [sum(nets[d][int(rng.integers(0, len(sn170.ARMS)))] for d in tdays) for _ in range(500)]
    res["candidates"]["SN170 bandit"] = {"test_net_mean": round(float(np.mean(seeds))), "seed_min": round(float(np.min(seeds))),
                                         "seed_max": round(float(np.max(seeds))), "random_play_p95": round(float(np.percentile(rnd, 95))),
                                         "fixed_arms_test": {a: round(sum(nets[d][k] for d in tdays)) for k, a in enumerate(sn170.ARMS)},
                                         "dev_pass": res_of("sn170")["dev_pass"]}

    # --- SN171 the volatility forecast (the only development pass)
    f171 = load("sn171_final.pkl")
    har = p3.HAR(TEST)
    rho = {}
    for S in TEST:
        fs, si = har.sigma(S.day, f171["beta"], f171["s2"]), C.sigma_imp(S, p3.I1000)
        if fs and si:
            rho[S.day] = fs / si
    r171 = res_of("sn171")
    for wname, (wallet, kind, room) in (("Rs 15k strangle", (15000.0, "strangle1", 3000.0)), ("Rs 30k straddle", (30000.0, "straddle", 6000.0))):
        _kk, kappa, exn = r171[wname]["final_variant"].split()
        kappa, tgt = float(kappa), (0.10 * wallet if exn == "wage" else None)

        def nets_at(stress=205.0, i=p3.I1000):
            return {S.day: p3.structure(S, i, kind, wallet, room, tgt, stress) for S in TEST}
        base, s400, late = nets_at(), nets_at(400.0), nets_at(i=p3.I1000 + 1)
        dn = {d: n for d, n in base.items() if n is not None and rho.get(d, 0) >= kappa}
        pool = {d: n for d, n in base.items() if n is not None}
        p95, wshare, nmean = random_day_null(pool, len(dn), wallet, tdays)
        v = verdict(dn, tdays, wallet, p95, wshare, sum(s400[d] for d in dn if s400.get(d) is not None),
                    sum(late[d] for d in dn if late.get(d) is not None), r171[wname]["dev_pass"])
        v["null_mean"] = nmean
        v["days"] = sorted(dn)
        res["candidates"][f"SN171 {wname} (kappa {kappa} {exn})"] = v

    # --- SN172-SN174 finals (failed development; scored for the record)
    for name, fn in (("SN172 " + res_of("sn172")["final_variant"], lambda S: p4.companion_net(("sn172", res_of("sn172")["final_variant"]), S, rho)),
                     ("SN173 " + res_of("sn173")["final_variant"], lambda S: p4.companion_net(("sn173", res_of("sn173")["final_variant"]), S, rho)),
                     ("SN174 " + res_of("sn174")["final_variant"], lambda S: p4.companion_net(("sn174", res_of("sn174")["final_variant"]), S, rho))):
        dn = {S.day: fn(S) for S in TEST}
        dn = {d: n for d, n in dn.items() if n is not None}
        res["candidates"][name] = {"net": round(sum(dn.values())), "trade_days": len(dn), "dev_pass": False}

    # --- SN175 the 1-second learned exit (latest 5% of 1-second days)
    t175 = load("sn175_test.pkl")
    rows = t175["rows"]
    first = {}
    for r, (i, _k) in enumerate(rows):
        first.setdefault(i, r)
    n_all = max(i for i, _k in rows) + 1
    offset = n_all - len(t175["E_test"])
    out175 = {"hold 60s": 0.0, "hold 180s": 0.0, "learned": 0.0, "entries": len(t175["E_test"])}
    for q, e in enumerate(t175["E_test"]):
        a = first[offset + q]
        pr = t175["P_rows"][a: a + len(e["seq"])]
        v = None
        for (t, val, _y, _x), p_ in zip(e["seq"], pr):
            if p_ == p_ and p_ < t175["phi"]:
                v = val
                break
        out175["learned"] += v if v is not None else e["seq"][-1][1]
        out175["hold 60s"] += e["fixed"][60] or 0.0
        out175["hold 180s"] += e["fixed"][180] or 0.0
    res["candidates"]["SN175 1-second learned exit"] = {k: (round(v) if isinstance(v, float) else v) for k, v in out175.items()} | {
        "test_days": t175["test_days"], "dev_pass": res_of("sn175")["dev_pass"]}

    # --- SN176 the wage day player on TEST
    comps = p4.passing_companions()
    w = sn176.watches(set(tdays))
    for key in ("Rs 15k", "Rs 30k growing (production)"):
        wallet = p4.WALLETS[key][1]
        g = p4.gold(key, keep=pw.is_test)
        player = p4.day_player({**w, **g}, TEST, comps, rho, wallet)
        res["reference"][f"SN176 wage day player {key}"] = pw.wage_stats(player, tdays, wallet)
    res["passing"] = [k for k, v in res["candidates"].items() if isinstance(v, dict) and v.get("PASS")]
    print("SN181", json.dumps({"candidates": res["candidates"], "passing": res["passing"]}, default=float)[:6000], flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
