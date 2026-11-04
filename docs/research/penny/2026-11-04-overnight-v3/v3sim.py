"""Overnight v3 research simulator (research only: no broker, scheduler or runtime state).

Post-close entry at the official close, sale at the next opening auction less ``exit_bps``.
No regular-session sleeve: Production's forward paper record (Oct 22 - Nov 3 2026) shows
15:20 fills averaging ~1.35% above the official close, so a regular-session buy is not a
cheap fallback. Accounting is the enrichment study's: fixed Rs 25,000, positive profits
withheld, losses reduce the next day's own risk capital, both tickets funded from free cash.

Fill models (all are assumptions, never evidence of fills):
  full         every post-close order fills.
  adversarial  a share (1 - f) of tickets that would have won are denied, ticket by ticket.
  correlated   one draw per night: with probability (1 - f) every winning ticket that night is denied.
  capacity     the post-close session can give us at most ``kappa`` x the day's share volume;
               combinable with adversarial/correlated denial.
Denial labels are read only at settlement; they never change selection, size or reserved cash.
"""
from __future__ import annotations

import hashlib
import math
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
V2DIR = ROOT / "docs/research/penny/2026-11-04-overnight-v2"
if str(V2DIR) not in sys.path:
    sys.path.insert(0, str(V2DIR))
import lab  # noqa: E402  (the parity-checked overnight-v2 lab)

DAYS = {
    "1518": (ROOT / "docs/research/penny/2026-11-04-overnight-enrichment/_local/older/days.pkl", "2015-01-01", "2018-12-31"),
    "1922": (V2DIR / "_local/days-yahoo.pkl", "2019-04-01", "2022-12-30"),
    "2326": (V2DIR / "_local/days-yahoo.pkl", "2023-01-01", "2026-10-30"),
    "kite": (V2DIR / "_local/days-kite.pkl", "2025-07-01", "2026-09-30"),
}


@dataclass(frozen=True)
class Policy:
    name: str
    slots: int = 2
    depth: int | None = 10          # None = every candidate of the day
    night_min: float = .001
    rank: str = "strength"          # strength (shipped order) | night (shrunk 60-night mean)
    min_day_value: float = 0.0      # Rs traded today; 0 = off
    filler: str = ""                # "" | F3 | F5: non-EDGE overnight names used after the EDGE pool
    filler_order: str = "night"     # night | value (today's traded value, liquidity first)
    edge_pool: bool = True          # False = fillers only (no EDGE candidates)
    cap_kappa: float = 0.0          # decision-time capacity rule: reserve at most this share of today's
                                    # share volume; a name below a quarter ticket is skipped (slot kept)
    extra: dict = field(default_factory=dict, hash=False, compare=False)

    def __post_init__(self):
        if self.rank not in ("strength", "night", "night_hi20", "strength_hi20", "night_cap", "random"):
            raise ValueError("unknown rank")
        if self.slots < 1:
            raise ValueError("slots")


@dataclass(frozen=True)
class FillModel:
    name: str = "full"
    win_fill: float = 1.0           # share of winning tickets that fill
    correlated: bool = False
    kappa: float | None = None      # capacity as a share of the day's share volume
    exit_bps: float = 5.0

    def label(self):
        return self.name


def _u(*parts) -> float:
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "big") / 2 ** 64


@dataclass
class Filler:
    """A non-EDGE overnight candidate built from causal daily features (no stop, no strength)."""
    ticker: str
    close: float
    f: dict
    kind: str = "FILL"
    stop: float = 0.0


def filler_table(days):
    """date -> list of Filler for every band ticker (5 <= close <= 55), features from that day and earlier only.

    Mirrors lab._causal_features: 60 nights including today's open night (clipped +-5%, shrunk by
    n/(n+20)), rvol against the median of the prior 20 sessions' volume, 20-session high incl. today."""
    from collections import deque
    import statistics as st
    nights, vols, highs, out = {}, {}, {}, {}
    for d in days:
        today = []
        for t, b in d.bar.items():
            if t == "NIFTYBEES" or t.endswith(("-SM", "-ST")) or b["volume"] <= 0:
                continue
            pc = d.prev_close.get(t)
            nq = nights.setdefault(t, deque(maxlen=60)); vq = vols.setdefault(t, deque(maxlen=20)); hq = highs.setdefault(t, deque(maxlen=20))
            prior_vol = list(vq)
            if pc and pc > 0:
                nq.append(max(-.05, min(.05, b["open"] / pc - 1)))
            vq.append(b["volume"]); hq.append(b["high"])
            if not pc or pc <= 0 or len(prior_vol) < 20 or len(nq) < 20 or not 5 <= b["close"] <= 55:
                continue
            med = st.median(prior_vol)
            h, l, c = b["high"], b["low"], b["close"]
            f = {"ret": c / pc - 1, "clv": (c - l) / (h - l) if h > l else .5, "rvol": b["volume"] / med if med > 0 else 0.,
                 "night_mean": sum(nq) / len(nq) * len(nq) / (len(nq) + 20), "near_hi20": c / max(hq) - 1,
                 "tv": c * b["volume"], "from_high": c / h - 1}
            today.append(Filler(t, c, f))
        out[d.date] = today
    return out


FILL_RULES = {
    "F3": lambda f: f["ret"] >= .05 and f["clv"] >= .5 and f["rvol"] >= 2 and f["night_mean"] >= .001,
    "F5": lambda f: f["night_mean"] >= .005 and f["ret"] >= .02,
}
_FILL_CACHE = {}


def fillers(days, day, p):
    key = id(days)
    if key not in _FILL_CACHE:
        _FILL_CACHE[key] = filler_table(days)
    rule = FILL_RULES[p.filler]
    out = []
    for c in _FILL_CACHE[key].get(day.date, []):
        f = c.f
        if f["from_high"] >= -.001 and f["ret"] >= .019:          # the shipped realism refusal
            continue
        if rule(f):
            out.append(c)
    if p.filler_order == "value":
        out.sort(key=lambda c: -c.f["tv"])
    elif p.filler_order == "random":          # ranking null: same fillers, random order
        out.sort(key=lambda c: _u(p.extra["null_seed"], day.date, c.ticker, "fill"))
    else:
        out.sort(key=lambda c: -c.f["night_mean"])
    return out


def pool(day, p: Policy, days=None) -> list:
    base = _edge_pool(day, p) if p.edge_pool else []
    if not p.filler:
        return base
    seen = {c.ticker for c in base}
    extra = [c for c in fillers(days, day, p) if c.ticker not in seen]
    if not p.edge_pool and p.rank == "strength_hi20":
        extra.sort(key=lambda c: -(c.f.get("near_hi20", -1) > -.01))
    return base + extra


def _edge_pool(day, p: Policy) -> list:
    src = day.cands if p.depth is None else day.cands[:p.depth]
    src = [c for c in src if c.f.get("night_mean", 0) >= p.night_min]
    out = []
    for c in src:
        b = day.bar.get(c.ticker)
        pc = day.prev_close.get(c.ticker)
        if not b or b["volume"] <= 0 or c.kind == "MR_mid" or c.ticker.endswith(("-SM", "-ST")):
            continue
        if pc and b["close"] >= b["high"] * .999 and b["close"] / pc - 1 >= .019:
            continue
        if p.min_day_value and b["close"] * b["volume"] < p.min_day_value:
            continue
        out.append(c)
    if p.rank == "night":
        out.sort(key=lambda c: -c.f.get("night_mean", 0))
    elif p.rank == "night_hi20":
        out.sort(key=lambda c: (-(c.f.get("near_hi20", -1) > -.01), -c.f.get("night_mean", 0)))
    elif p.rank == "strength_hi20":           # stable: shipped strength order inside each group
        out.sort(key=lambda c: -(c.f.get("near_hi20", -1) > -.01))
    elif p.rank == "random":                  # ranking null: same pool, random order
        out.sort(key=lambda c: _u(p.extra["null_seed"], day.date, c.ticker))
    elif p.rank == "night_cap":               # night mean x the share of a half ticket 0.1% of today's volume covers
        def score(c):
            vol = day.bar[c.ticker]["volume"]
            return c.f.get("night_mean", 0) * min(1.0, .001 * vol * c.close / 12500.0)
        out.sort(key=lambda c: -score(c))
    return out


def simulate(days, p: Policy, fm: FillModel, *, start, end, bankroll=25000., seed=20261104, keep=False):
    cash = bankroll
    realized = 0.
    held = {}
    trades = []
    curve = []
    out = Counter()
    for d in days:
        if d.date < start:
            continue
        night_u = _u(seed, "night", d.date)
        for t in sorted(held):
            pos = held[t]
            b = d.bar.get(t)
            if not b or b["volume"] <= 0:
                pos["delayed"] = True
                continue
            exit_price = b["open"] * (1 - fm.exit_bps / 10000)
            ref_qty = int((bankroll / 2) // (pos["close"] * 1.002))
            win = ref_qty > 0 and (exit_price - pos["close"]) * ref_qty - lab.cnc_costs(pos["close"], exit_price, ref_qty) > 0
            denied = False
            if win and fm.win_fill < 1:
                u = pos["night_u"] if fm.correlated else _u(seed, pos["day"], t)   # the enrichment study's draw
                denied = u >= fm.win_fill
            qty = 0 if denied else pos["qty"]
            cash += (pos["qty"] - qty) * pos["close"]
            out["DENIED_WINNER" if denied else "FILLED"] += 1
            if qty:
                fees = lab.cnc_costs(pos["close"], exit_price, qty)
                net = (exit_price - pos["close"]) * qty - fees
                cash += exit_price * qty - fees
                realized += net
                tr = {"ticker": t, "entry_date": pos["day"], "exit_date": d.date, "entry": pos["close"],
                      "exit": exit_price, "shares": qty, "net": net, "cost": fees,
                      "notional": qty * pos["close"], "kind": pos["kind"], "delayed": pos.get("delayed", False)}
                trades.append(tr if keep else {k: tr[k] for k in ("net", "entry_date", "notional")})
            del held[t]
        if d.date <= end:
            risk_capital = min(bankroll, bankroll + realized)
            entered = 0
            for c in pool(d, p, days):
                if entered >= p.slots:
                    break
                if c.ticker in held or c.ticker.split("-")[0] in {x.split("-")[0] for x in held}:
                    continue
                free = cash - max(realized, 0.)
                budget = free / (p.slots - entered)
                if budget <= 0:
                    out["NO_FREE_CASH"] += 1
                    continue
                qty = int(budget // (c.close * 1.002))
                qty = min(qty, int(risk_capital / p.slots // c.close))
                vol = d.bar[c.ticker]["volume"]
                qty = min(qty, int(.01 * c.close * vol // c.close))  # the enrichment study's 1% day cap
                plan = int(risk_capital / p.slots / c.close)
                if p.cap_kappa:
                    qty = min(qty, int(p.cap_kappa * vol))
                fill_qty = min(qty, int(fm.kappa * vol)) if fm.kappa is not None else qty
                if qty < 1 or qty < .25 * plan:
                    out["LIQUIDITY_OR_DUST"] += 1
                    continue
                if c.stop >= c.close:
                    out["STOP_REFERENCE_BREACHED"] += 1
                    continue
                cash -= qty * c.close
                cash += (qty - fill_qty) * c.close                  # unfilled capacity returns at once
                if fill_qty < 1:
                    out["CAPACITY_NONFILL"] += 1
                    entered += 1
                    continue
                if fill_qty < qty:
                    out["CAPACITY_PARTIAL"] += 1
                entered += 1
                held[c.ticker] = {"day": d.date, "close": c.close, "qty": fill_qty, "kind": c.kind, "night_u": night_u}
        marked = cash + sum((d.bar[t]["close"] if t in d.bar else pos["close"]) * pos["qty"] for t, pos in held.items())
        curve.append((d.date, marked))
        if d.date > end and not held:
            break
    s = lab.summarize(trades, curve, bankroll)
    s["dd_pct_initial"] = round(100 * s["dd"] / bankroll, 3)
    return {"policy": asdict(p), "fill": asdict(fm), "summary": s, "outcomes": dict(out),
            "open_at_end": len(held), "trades": trades}


def load_days(cache={}):
    for name, (path, s, e) in DAYS.items():
        if path not in cache:
            cache[path] = lab.load(path)
    return {name: (cache[path], s, e) for name, (path, s, e) in DAYS.items()}


def by_year(trades):
    y = Counter()
    for t in trades:
        y[t["entry_date"][:4]] += t["net"]
    return {k: round(v) for k, v in sorted(y.items())}
