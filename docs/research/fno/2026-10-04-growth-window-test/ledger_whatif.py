"""Approximate what-if: the NEW sizing/brakes applied to the ACTUAL paper single-leg trades.

Only removes or resizes trades the live book really took (it cannot invent new
ones). P&L per lot is scaled linearly (flat per-order fees make this slightly
approximate). Capped-loss (DR) closes are kept as they happened, at 1 lot.
"""
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

ENGINE = r"C:\Users\Urveesh\Desktop\trading-sentinel\python-engine"
sys.path.insert(0, ENGINE)
os.chdir(ENGINE)

import pytz  # noqa: E402
from config import settings  # noqa: E402
from fno_adaptive_risk import Close, policy_from_settings as adaptive_policy, risk_stance  # noqa: E402
from fno_risk import lots_for_pool  # noqa: E402
from fno_shared_risk import entry_halts, policy_from_settings  # noqa: E402

IST = pytz.timezone("Asia/Kolkata")
DB = r"C:\Users\Urveesh\Desktop\trading-sentinel\docs\research\fno\2026-10-04-archive\_local\fno-replay.sqlite"
LOT = 65
BANKROLL = float(sys.argv[1]) if len(sys.argv) > 1 else 250_000.0
settings.FNO_PAPER_BANKROLL = BANKROLL


def aware(stamp):
    at = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    return at if at.tzinfo else IST.localize(at)


con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
single = [(aware(e), aware(x), lots, prem, pnl, sym) for e, x, lots, prem, pnl, sym in con.execute(
    "SELECT entry_time, exit_time, lots, entry_premium, pnl, tradingsymbol FROM fno_positions "
    "WHERE source='FNO_PAPER' AND status='CLOSED' ORDER BY entry_time")]
dr = [(aware(c), float(p)) for c, p in con.execute(
    "SELECT closed_at, pnl FROM fno_dr_positions WHERE source='FNO_PAPER' AND status='CLOSED'")]


def run(new_rules: bool):
    closes = [Close(at, pnl, False) for at, pnl in dr]          # DR history as it happened
    cash = [(at, pnl) for at, pnl in dr]
    taken, skipped = [], defaultdict(int)
    for entry, exit_, lots, prem, pnl, sym in single:
        if not new_rules:
            new_lots = lots
        else:
            visible = [(a, p) for a, p in cash if a <= entry]
            equity = BANKROLL + sum(p for _, p in visible)
            stance = risk_stance(closes, allocation=BANKROLL, now=entry, policy=adaptive_policy())
            halts = entry_halts(trade_cash=visible, completed_newest_first=sorted(visible, reverse=True),
                                today_ist=entry.astimezone(IST).date(), pool_rs=BANKROLL, equity_rs=equity,
                                policy=policy_from_settings()).active
            if stance.single_leg_halted_today:
                halts = (*halts, "two_strike_day_halt")
            if halts:
                skipped[halts[0].split(" ")[0]] += 1
                continue
            m = stance.multiplier
            ceiling = settings.FNO_MAX_LOTS_PROVEN if m > 1 else settings.FNO_MAX_LOTS

            def size(scale, cap):
                return lots_for_pool(equity, prem, LOT, settings.FNO_STOP_PREMIUM_PCT,
                                     settings.FNO_MAX_RISK_PCT * scale, cap,
                                     max_risk_rupees=settings.FNO_MAX_LOSS_PER_TRADE * scale)
            new_lots = size(m, ceiling)
            if new_lots < 1 and 0 < m < 1:
                new_lots = size(1.0, 1)
            if new_lots < 1:
                skipped["pool_below_min_viable"] += 1
                continue
        scaled = pnl / lots * new_lots
        taken.append((exit_, scaled, sym, new_lots))
        closes.append(Close(exit_, scaled, True))
        cash.append((exit_, scaled))
    return taken, skipped


def report(label, taken, skipped):
    by_day, by_month = defaultdict(float), defaultdict(float)
    for at, p, *_ in taken:
        by_day[at.astimezone(IST).date()] += p
    for at, p in dr:
        by_day[at.astimezone(IST).date()] += p
    for d, p in by_day.items():
        by_month[d.strftime("%Y-%m")] += p
    equity = peak = dd = 0.0
    streak = worst_streak = 0
    for d in sorted(by_day):
        equity += by_day[d]
        peak, dd = max(peak, equity), max(dd, peak - equity)
        streak = streak + 1 if by_day[d] < 0 else 0
        worst_streak = max(worst_streak, streak)
    single_net = sum(p for _, p, *_ in taken)
    print(f"\n== {label} (bankroll {BANKROLL:,.0f})")
    print(f"  single-leg trades {len(taken)}  net {single_net:,.0f}   + DR {sum(p for _, p in dr):,.0f}"
          f"   = total {single_net + sum(p for _, p in dr):,.0f}")
    print(f"  worst day {min(by_day.values()):,.0f}  max drawdown {dd:,.0f}  losing days "
          f"{sum(v < 0 for v in by_day.values())}/{len(by_day)}  longest losing streak {worst_streak} days")
    print("  by month:", {k: round(v) for k, v in sorted(by_month.items())})
    if skipped:
        print("  skipped:", dict(skipped))


for label, flag in (("ACTUAL (old rules, as traded)", False), ("NEW rules what-if", True)):
    report(label, *run(flag))
