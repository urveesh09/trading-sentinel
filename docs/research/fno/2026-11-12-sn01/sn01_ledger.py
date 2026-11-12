"""SN01 wallet ledger - the owner's wallet, target and refill rules played day by day (research only).

Rules (owner, Nov 12, 2026):
  * the wallet W starts at Rs 15,000; profits are banked and never traded; a losing day is refilled by the owner,
    so every day starts with the same W;
  * the day's loss limit is 20% of the current W;
  * when the profit banked since the last step reaches 100% of the current W, W grows by 50% (the step's profit is
    used up; any excess carries to the next step). Primary reading: the NET of winning and losing days, because a
    refill is the owner's own money. The gross reading (winning days only) is reported beside it;
  * the day target starts at Rs 1,500 (10% of the starting wallet) and, as the owner chose, grows by 50% once every
    2 wallet steps ("every2") or every 3 ("every3"); "prop" (10% of the current W) and "flat" (always Rs 1,500) are
    shown for comparison.
"""
from __future__ import annotations

import sn01_sim as M

START_WALLET = 15000.0
START_TARGET = 1500.0
LOSS_SHARE = 0.20


def target_for(mode: str, steps: int, wallet: float) -> float:
    if mode == "every2":
        return START_TARGET * 1.5 ** (steps // 2)
    if mode == "every3":
        return START_TARGET * 1.5 ** (steps // 3)
    if mode == "prop":
        return 0.10 * wallet
    if mode == "flat":
        return START_TARGET
    raise ValueError(mode)


def play(sessions: list, g: dict, mode: str, stress: float, counting: str = "net") -> dict:
    wallet, steps, progress = START_WALLET, 0, 0.0
    total, refills, banked_wins = 0.0, 0.0, 0.0
    days, step_days = [], []
    peak, max_dd, cum = 0.0, 0.0, 0.0
    streak, worst_streak = 0, 0
    for S in sessions:
        target = target_for(mode, steps, wallet)
        loss = LOSS_SHARE * wallet
        r = M.run_day(S, g, wallet, target, loss, stress)
        net = r["net"]
        total += net
        cum += net
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
        if net < 0:
            refills += -net
            streak += 1
            worst_streak = max(worst_streak, streak)
        else:
            if net > 0:
                banked_wins += net
            streak = 0 if net > 0 else streak
        progress += net if counting == "net" else max(net, 0.0)
        while progress >= wallet:
            progress -= wallet
            wallet *= 1.5
            steps += 1
            step_days.append({"day": S.day, "new_wallet": round(wallet), "target_now": round(target_for(mode, steps, wallet))})
        days.append({"day": S.day, "net": round(net, 2), "end": r["end"], "trades": r["trades"], "wallet": round(wallet),
                     "target": round(target), "loss_limit": round(loss)})
    return {"mode": mode, "stress": stress, "counting": counting, "sessions": len(sessions), "total_net": round(total),
            "refilled": round(refills), "won_on_green_days": round(banked_wins), "final_wallet": round(wallet),
            "wallet_steps": steps, "step_days": step_days,
            "target_days": sum(1 for d in days if d["end"] == "target"),
            "loss_limit_days": sum(1 for d in days if d["end"] == "loss_limit"),
            "green_days": sum(1 for d in days if d["net"] > 0), "red_days": sum(1 for d in days if d["net"] < 0),
            "flat_days": sum(1 for d in days if d["net"] == 0),
            "worst_day": round(min(d["net"] for d in days)), "best_day": round(max(d["net"] for d in days)),
            "max_fall": round(max_dd), "longest_red_streak": worst_streak, "days": days}
