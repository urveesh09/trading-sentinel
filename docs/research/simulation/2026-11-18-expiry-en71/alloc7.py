"""EN79 (a cash-aware selector without hindsight switching) and EN80 (one shared wallet) - PLAN7.md.

EN79: four frozen experts - CASH, matched E03, EN72's marketable scout and the original EN60 CUSUM setup with both sides,
all in the matched envelope and fill model. Before each expiry the selector takes the expert with the highest log
weight (ties: CASH, then the listed order); weights start equal and, after the session closes, every expert's log
weight moves by 0.1 x clip(net / 2500, -1, 1) from its fixed-cap shadow ledger (CASH earns 0). Log-weight spreads are
capped at 10 (numerical safety). No intraday switching, no reset, no parameter search. Immutable receipts: the
pre-session weights, the chosen expert, the post-session update.

EN80: the engine - one wallet over both indices' sessions in date order (no same-date expiries exist in these books;
the engine refuses one), the unchanged 1,500 / 3,000 / 4,000 brakes on the trading high-water, the 50% sweep, one
open position and a single Rs 2,500 day room. Admissions are recomputed at the current cash and brake state, never
stitched from fixed-ticket P&Ls. Checks: cash conservation, reservations within room, restart equivalence. Calendar-
week block scenarios (2 / 4 / 8 weeks, both indices and missing weeks retained) are conditional scenarios, not
probabilities. With no forward-eligible candidate the engine runs only labelled fixtures."""
from __future__ import annotations
import math, sys
from collections import defaultdict
from datetime import date
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import en_lab7 as L7  # noqa: E402

L6, E = L7.L6, L7.E
EXPERTS = ("CASH", "E03_env", "EN72", "EN60_env")
L7.ARMS["EN60_env"] = L7.R7(L7.E032, setup3="CUSUM", chase=.04, hold=15, underlying_stop=0., **L7.ENV7)
ETA, CAP = .1, 10.


def expert_days(book, scenario="ordinary"):
    """{expert: [day result]} fixed-cap shadow ledgers on the same sessions (CASH: zero days)."""
    out = {"CASH": [dict(day=t.day, net=0., trades=0, fees=0., unresolved=0, marked_worst=0., spent=0., intents=0, minutes_in=0) for t in book]}
    for e in EXPERTS[1:]:
        arm = L7.ARMS[e]
        out[e] = [L7.day7(t, arm, scenario, 30000., L7.budget_of(arm), True) for t in book]
    return out


def select(shadow, days):
    """Receipts per session: pre-session log weights, chosen expert, post-session update; from matured sessions only."""
    w = {e: 0. for e in EXPERTS}; rec = []
    for s, day in enumerate(days):
        pre = dict(w)
        chosen = max(EXPERTS, key=lambda e: (round(w[e], 12), -EXPERTS.index(e)))
        upd = {e: ETA * max(-1., min(1., shadow[e][s]["net"] / 2500.)) for e in EXPERTS}
        for e in EXPERTS:
            w[e] += upd[e]
        top = max(w.values())
        for e in EXPERTS:
            w[e] = max(w[e], top - CAP)
        rec.append(dict(day=day, pre=pre, chosen=chosen, update=upd))
    return rec


def selector_days(book, shadow, rec, rule="hedge"):
    """Fixed-cap selector ledger (the chosen expert's shadow day), and the controls' choices."""
    out = []
    for s, t in enumerate(book):
        if rule == "hedge":
            e = rec[s]["chosen"]
        elif rule == "round_robin":
            e = EXPERTS[s % len(EXPERTS)]
        else:
            e = rule
        out.append(dict(shadow[e][s], expert=e))
    return out


def selector_wallet(book, rec, scenario="ordinary", start=30000., retain=.5):
    """The chosen expert run at the wallet's own cash and brake each session (the weights stay the shadow ones)."""
    P = W = peakP = 0.; days = []; liq = 0.
    for s, t in enumerate(book):
        cash = start + P - W; dd = peakP - P
        scale = 0. if dd >= 4000 else .25 if dd >= 3000 else .5 if dd >= 1500 else 1.
        e = rec[s]["chosen"]
        if e == "CASH":
            row = dict(day=t.day, net=0., trades=0, marked_worst=0., fees=0., unresolved=0)
        else:
            arm = L7.ARMS[e]; row = L7.day7(t, arm, scenario, cash, min(L7.budget_of(arm) * scale, cash), False)
        liq = max(liq, peakP - (P + min(0., row.get("marked_worst", 0.))))
        P = round(P + row["net"], 2); peakP = max(peakP, P)
        sweep = round(max(0., retain * max(P, 0.) - W), 2); W = round(W + sweep, 2)
        row.update(scale=scale, P=P, W=W, expert=e); days.append(row)
    return dict(days=days, P=P, swept=W, wallet=round(start + P - W, 2), halted=sum(d["scale"] == 0. for d in days),
                first_halt=next((d["day"] for d in days if d["scale"] == 0.), None), liq_dd=round(liq, 2))


def en79(book, scenario="ordinary"):
    days = [t.day for t in book]; sh = expert_days(book, scenario); rec = select(sh, days)
    res = {"EN79": selector_days(book, sh, rec), "EN79_round_robin_ctl": selector_days(book, sh, rec, "round_robin")}
    for e in EXPERTS:
        res[f"fixed_{e}"] = selector_days(book, sh, rec, e)
    tot = {e: sum(d["net"] for d in sh[e]) for e in EXPERTS}
    best = max(EXPERTS, key=lambda e: tot[e])
    res["retrospective_best_UNTRADEABLE"] = selector_days(book, sh, rec, best)
    chosen = defaultdict(int)
    for r in rec:
        chosen[r["chosen"]] += 1
    # missed recovery winners: CASH chosen while the best fixed expert made >= Rs 1,250 that session
    missed = [dict(day=r["day"], best_net=sh[best][s]["net"]) for s, r in enumerate(rec) if r["chosen"] == "CASH" and sh[best][s]["net"] >= 1250]
    return dict(days=res, receipts=rec, chosen=dict(chosen), best_fixed=best, totals={e: round(v, 2) for e, v in tot.items()}, missed_winners=missed,
                shadow=sh)


# ---------------------------------------------------------------- EN80: one shared wallet
def sessions(B):
    xs = [(t.day, 0, t) for t in B["NIFTY"]] + [(t.day, 1, t) for t in B["SENSEX"]]
    xs.sort(key=lambda x: (x[0], x[1]))
    ds = [x[0] for x in xs]
    assert len(ds) == len(set(ds)), "same-date sessions need a minute-interleaved engine"
    return [x[2] for x in xs]


def shared_wallet(seq, members, scenario="ordinary", start=30000., retain=.5, day_room=2500., state=None, stop_at=None):
    """members: {und: arm}. Returns days + the state, so a stopped run can be resumed (restart equivalence)."""
    st = dict(P=0., W=0., peakP=0., liq=0.) if state is None else dict(state)
    days = []
    for n, t in enumerate(seq):
        if stop_at is not None and n >= stop_at:
            break
        cash = start + st["P"] - st["W"]; dd = st["peakP"] - st["P"]
        scale = 0. if dd >= 4000 else .25 if dd >= 3000 else .5 if dd >= 1500 else 1.
        arm = members.get(L7.und(t))
        if arm is None:
            row = dict(day=t.day, net=0., trades=0, marked_worst=0., spent=0.)
        else:
            budget = min(day_room, L7.budget_of(arm)) * scale
            row = L7.day7(t, arm, scenario, cash, min(budget, cash), False)
            assert row["net"] >= -min(budget, cash) - .05, (t.day, row["net"], budget)        # never beyond the room
        st["liq"] = max(st["liq"], st["peakP"] - (st["P"] + min(0., row.get("marked_worst", 0.))))
        st["P"] = round(st["P"] + row["net"], 2); st["peakP"] = max(st["peakP"], st["P"])
        sweep = round(max(0., retain * max(st["P"], 0.) - st["W"]), 2); st["W"] = round(st["W"] + sweep, 2)
        assert abs((start + st["P"] - st["W"]) + st["W"] - (start + st["P"])) < 1e-6 and start + st["P"] - st["W"] >= -.01
        row.update(und=L7.und(t), scale=scale, P=st["P"], W=st["W"], cash_after=round(start + st["P"] - st["W"], 2)); days.append(row)
    return dict(days=days, state=st, P=st["P"], swept=st["W"], wallet=round(start + st["P"] - st["W"], 2),
                halted=sum(d["scale"] == 0. for d in days), first_halt=next((d["day"] for d in days if d["scale"] == 0.), None), liq_dd=round(st["liq"], 2))


def restart_check(seq, members):
    full = shared_wallet(seq, members); half = len(seq) // 2
    a = shared_wallet(seq, members, stop_at=half); b = shared_wallet(seq[half:], members, state=a["state"])
    same = [x["net"] for x in full["days"]] == [x["net"] for x in a["days"] + b["days"]] and full["state"] == b["state"]
    return dict(sessions=len(seq), split_at=half, identical=bool(same))


def week_blocks(seq, rows):
    """Calendar ISO weeks from the first to the last session; every week present (empty weeks kept as zero sessions)."""
    by = defaultdict(list)
    for t, r in zip(seq, rows):
        y, w, _ = date.fromisoformat(t.day).isocalendar(); by[(y, w)].append(r)
    d0, d1 = date.fromisoformat(seq[0].day), date.fromisoformat(seq[-1].day); out = []; d = d0
    from datetime import timedelta
    while d <= d1 + timedelta(days=6):
        y, w, _ = d.isocalendar()
        if not out or out[-1][0] != (y, w):
            out.append(((y, w), by.get((y, w), [])))
        d += timedelta(days=7)
    return [x[1] for x in out]


def scenarios(seq, pre, block_weeks=(2, 4, 8), paths=1000, horizon_weeks=52, seed=20261119, start=30000.):
    """Moving-block bootstrap of calendar weeks. `pre[sc][scale]` holds each session's day result at each brake
    scale (recomputed admissions per scale), so a resampled path re-applies the brake; ordinary and adverse share the
    same sampled calendars."""
    out = {}
    for b in block_weeks:
        rng = np.random.default_rng(seed + b); res = {}
        weeks = week_blocks(seq, list(range(len(seq))))
        nb = len(weeks) - b + 1
        cal = [np.concatenate([rng.integers(0, nb, 1) for _ in range(math.ceil(horizon_weeks / b))]) for _ in range(paths)]
        for sc in pre:
            halts = 0; Ps = []
            for c in cal:
                P = peak = 0.; halted = False
                for k in c:
                    for wk in weeks[k:k + b]:
                        for n in wk:
                            dd = peak - P; scale = 0. if dd >= 4000 else .25 if dd >= 3000 else .5 if dd >= 1500 else 1.
                            if scale == 0.:
                                halted = True
                            P += pre[sc][scale][n]; peak = max(peak, P)
                halts += halted; Ps.append(P)
            res[sc] = dict(halt_share=round(halts / paths, 4), median_P=round(float(np.median(Ps)), 2), p05_P=round(float(np.percentile(Ps, 5)), 2),
                           share_losing=round(float(np.mean(np.array(Ps) < 0)), 4))
        out[f"{b}w"] = res
    return dict(scenarios=out, note="conditional scenarios resampled from seen sessions: not probabilities for next year")


def en80(B, members):
    seq = sessions(B)
    out = dict(fixture={k: v for k, v in members.items()}, members_note="engine fixture, not an eligible candidate")
    for sc in ("ordinary", "adverse"):
        w = shared_wallet(seq, {k: L7.ARMS[v] for k, v in members.items()}, sc)
        out[sc] = {k: w[k] for k in ("P", "swept", "wallet", "halted", "first_halt", "liq_dd")}
        out[sc]["by_index"] = {u: round(sum(d["net"] for d in w["days"] if d["und"] == u), 2) for u in ("NIFTY", "SENSEX")}
    out["restart"] = restart_check(seq, {k: L7.ARMS[v] for k, v in members.items()})
    pre = {}
    for sc in ("ordinary", "adverse"):
        pre[sc] = {}
        for scale in (1., .5, .25, 0.):
            pre[sc][scale] = []
            for t in seq:
                arm = L7.ARMS.get(members.get(L7.und(t), ""))
                if arm is None or scale == 0.:
                    pre[sc][scale].append(0.); continue
                pre[sc][scale].append(L7.day7(t, arm, sc, 30000., min(2500., L7.budget_of(arm)) * scale, False)["net"])
    out["scenarios"] = scenarios(seq, pre)
    return out
