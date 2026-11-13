"""Phase P4 helpers (SN176-SN180): Gold v5 day nets per wallet (SN110's player, v5 parity proven), the companions
that passed development (read from the P3 result files; the ML studies SN167-SN170 / SN175 failed development and are
excluded by the same rule), the wage day player ledger and the salary account."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import pw  # noqa: E402  (puts the SN116 folder on the path)
import pc  # noqa: E402

C = pw.C
HERE = Path(__file__).resolve().parent
WALLETS = {"Rs 15k": ("A 15k 1 lot", 15000.0, "one", None), "Rs 30k fixed": ("30k fixed", 30000.0, "grow", 0),
           "Rs 30k growing (production)": ("30k grow stop 3", 30000.0, "grow", 3),
           "Rs 50k growing": ("50k grow stop 3", 50000.0, "grow", 3),
           "Rs 1 lakh growing": ("100k grow stop 3", 100000.0, "grow", 3)}


def gold(wallet_key, v=None, keep=lambda d: True):
    _row, daylog = pc.gold_days(v or C.V5, WALLETS[wallet_key])
    return {d: n for d, n in daylog if n and keep(d)}


def passing_companions():
    """{name: day-net function(S, wallet) -> net or None} for every P3 rule whose results say dev_pass."""
    import p3
    import sn172
    import sn173
    import sn174
    out = {}
    r171 = _res("sn171")
    if r171:
        for wname, (wallet, kind, room) in (("Rs 15k strangle", (15000.0, "strangle1", 3000.0)),
                                             ("Rs 30k straddle", (30000.0, "straddle", 6000.0))):
            if r171[wname]["dev_pass"]:
                k, ex = r171[wname]["final_variant"].split()[1], r171[wname]["final_variant"].split()[2]
                out[f"SN171 {wname}"] = ("har", float(k), ex, wallet, kind, room)
    r172 = _res("sn172")
    if r172 and r172["dev_pass"]:
        out["SN172 " + r172["final_variant"]] = ("sn172", r172["final_variant"])
    r173 = _res("sn173")
    if r173 and r173["dev_pass"]:
        out["SN173 " + r173["final_variant"]] = ("sn173", r173["final_variant"])
    r174 = _res("sn174")
    if r174 and r174["dev_pass"]:
        out["SN174 " + r174["final_variant"]] = ("sn174", r174["final_variant"])
    return out


def _res(name):
    p = HERE / f"results-{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def companion_net(spec, S, rho):
    import p3
    import sn172
    import sn173
    import sn174
    kind = spec[0]
    if kind == "har":
        _k, kappa, ex, wallet, struct, room = spec
        if rho.get(S.day, 0) < kappa:
            return None
        return p3.structure(S, p3.I1000, struct, wallet, room, 0.10 * wallet if ex == "wage" else None)
    if kind == "sn172":
        v = spec[1]
        if v.startswith("strangle"):
            return p3.structure(S, sn172.I1315, "strangle1", 15000.0, 3000.0, 1500.0 if "wage" in v else None)
        return sn172.rb_after(S, 0 if v == "RB ATM" else 1)
    if kind == "sn173":
        _g, g, mode, at = spec[1].split()
        x = sn173.gap_atr(S)
        if x is None or abs(x) < float(g):
            return None
        d = (-1 if x > 0 else 1) if mode == "fade" else (1 if x > 0 else -1)
        return sn173.one(S, 5 if at == "@09:20" else 15, d)
    if kind == "sn174":
        if rho.get(S.day, 9) >= 1.0:
            return None
        return sn174.day(S, float(spec[1].split()[1]))
    return None


def comp_wallet(spec):
    return spec[3] if spec[0] == "har" else 15000.0


def day_player(gold_nets, sessions, comps, rho, wallet=15000.0, comp_scale=1.0):
    """Gold first; on Gold's empty days the first companion that trades, among those whose own sizing fits the account's
    wallet, largest first (a Rs 15k account never takes the Rs 30k straddle). Returns {day: net}."""
    out = dict(gold_nets)
    fit = sorted(((n, s) for n, s in comps.items() if comp_wallet(s) <= wallet), key=lambda x: -comp_wallet(x[1]))
    for S in sessions:
        if S.day in out:
            continue
        for _name, spec in fit:
            n = companion_net(spec, S, rho)
            if n is not None and n != 0:
                out[S.day] = n * comp_scale
                break
    return out


def salary(day_nets, days, start, wallet, wage):
    """Account: cash B starts at ``start``; each session B += that day's trading net (losses come out of B: the
    refill), then the wage is paid if B - wage >= wallet (else what is above the wallet). Returns the record."""
    B, paid, short_days, short_months, broke = float(start), 0.0, 0, set(), None
    low = B
    for d in days:
        B += float(day_nets.get(d, 0.0))
        if B < wallet and broke is None:
            broke = d
        pay = wage if B - wage >= wallet else max(0.0, B - wallet)
        if pay < wage - 1e-6:
            short_days += 1
            short_months.add(d[:7])
        B -= pay
        paid += pay
        low = min(low, B)
    months = len({d[:7] for d in days})
    return {"start": start, "paid": round(paid), "paid_per_month": round(paid / max(1, months)), "short_days": short_days,
            "short_months": len(short_months), "months": months, "end_balance": round(B), "lowest_balance": round(low),
            "first_day_below_wallet": broke}


def min_start(day_nets, days, wallet, wage, step=5000.0, cap=2_000_000.0):
    s = wallet
    while s <= cap:
        r = salary(day_nets, days, s, wallet, wage)
        if r["short_days"] == 0:
            return s
        s += step
    return None


def monthly(day_nets, days, wage):
    m = {}
    for d in days:
        m.setdefault(d[:7], []).append(float(day_nets.get(d, 0.0)))
    return {k: {"net": sum(v), "wage_days": sum(x >= wage - 1e-6 for x in v)} for k, v in m.items()}


def bootstrap_months(mrec, draws=4000, seed=179, months=12):
    rng = np.random.default_rng(seed)
    vals = list(mrec.values())
    nets = np.array([v["net"] for v in vals])
    wd = np.array([v["wage_days"] for v in vals])
    idx = rng.integers(0, len(vals), size=(draws, months))
    yr = nets[idx].sum(axis=1)
    return {"months": len(vals), "p_month_negative": round(float((nets < 0).mean()), 3),
            "p_month_15_wage_days": round(float((wd >= 15).mean()), 3), "p_month_10_wage_days": round(float((wd >= 10).mean()), 3),
            "year_net_p5": round(float(np.percentile(yr, 5))), "year_net_median": round(float(np.median(yr))),
            "p_year_negative": round(float((yr < 0).mean()), 3)}
