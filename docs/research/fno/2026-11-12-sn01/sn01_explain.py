"""SN01 explanation (descriptive, after the verdict; nothing here is a test or a selection).

1. Hindsight: on how many days could ONE lot of the ATM option have made the Rs 1,500 day after charges, if the
   direction had been known at 09:30? And how often did the other side fall far enough to hit Rs 3,000?
2. Luck: buy the ATM call or put at 09:30 at random and hold for +Rs 1,500 / -Rs 3,000 / 15:15. How often does the
   target come first, and what is the money? (The owner's payoff with no entry skill.)
3. The lock idea and the target growth on the final pick, one change at a time.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sn01_data as D  # noqa: E402
import sn01_ledger as LG  # noqa: E402
import sn01_sim as M  # noqa: E402

ENTRY = 15  # 09:30


def first_touch(S: M.Session, opt: str, qty: int, target: float, loss: float):
    c = S.F["c"][ENTRY]
    strike = int(round(c / 50) * 50)
    rec = S.option(strike, opt)
    if rec is None or not rec[6][ENTRY]:
        return None
    a, b_open, b_high, b_low, b_close, b_mark, traded = rec
    ask = M.ask_of(float(a[3][ENTRY]))
    tgt = ask + (target + M.charges(ask, ask, qty)) / qty
    stp = ask - (loss - M.charges(ask, ask, qty)) / qty
    best = -1e9
    for j in range(ENTRY + 1, M.EXIT_MIN + 1):
        if not traded[j]:
            continue
        best = max(best, b_high[j])
    hindsight = (best - ask) * qty - M.charges(ask, best, qty) if best > 0 else None
    for j in range(ENTRY + 1, M.EXIT_MIN + 1):
        if not traded[j]:
            continue
        if b_low[j] <= stp:
            x = min(stp, b_open[j])
            return "loss", (x - ask) * qty - M.charges(ask, x, qty), hindsight
        if b_high[j] >= tgt:
            x = max(tgt, b_open[j])
            return "target", (x - ask) * qty - M.charges(ask, x, qty), hindsight
    x = b_close[M.EXIT_MIN] if traded[M.EXIT_MIN] else b_mark[M.EXIT_MIN]
    return "eod", (x - ask) * qty - M.charges(ask, x, qty), hindsight


def main() -> None:
    out = {"hindsight_and_luck": {}, "final_pick_changes": {}}
    sessions = []
    for y in D.DATASETS:
        ys = [M.Session(s) for s in D.load_year(y)["sessions"].values()]
        sessions += ys
        rows = {"days": 0, "either_side_could_make_1500": 0, "right_side_could_make_1500": 0,
                "random_side": {"target": 0, "loss": 0, "eod": 0, "net": 0.0}}
        rng = np.random.default_rng(int(y))
        for S in ys:
            res = {opt: first_touch(S, opt, 65, 1500.0, 3000.0) for opt in ("CE", "PE")}
            if any(v is None for v in res.values()):
                continue
            rows["days"] += 1
            best = max(v[2] for v in res.values())
            rows["either_side_could_make_1500"] += best >= 1500
            # the side the index actually went by 15:15 (hindsight)
            right = "CE" if S.F["c"][M.EXIT_MIN] >= S.F["c"][ENTRY] else "PE"
            rows["right_side_could_make_1500"] += res[right][2] >= 1500
            pick = "CE" if rng.random() < 0.5 else "PE"
            kind, net, _ = res[pick]
            rows["random_side"][kind] += 1
            rows["random_side"]["net"] += net
        rows["random_side"]["net"] = round(rows["random_side"]["net"])
        out["hindsight_and_luck"][y] = rows
        print(y, rows, flush=True)
    final = json.loads((HERE / "results.json").read_text(encoding="utf-8"))["final"]["genome"]
    variants = {"final pick (lock 0.5)": final, "no lock (sell at the target)": {**final, "lock": 0.0},
                "lock 1.0": {**final, "lock": 1.0}, "lock 0.25": {**final, "lock": 0.25}}
    for name, g in variants.items():
        for stress in (0.0, 100.0):
            r = LG.play(sessions, g, "every2", stress)
            out["final_pick_changes"][f"{name} | +{int(stress)}"] = {k: r[k] for k in (
                "total_net", "wallet_steps", "target_days", "green_days", "red_days", "worst_day", "max_fall")}
            print(name, stress, out["final_pick_changes"][f"{name} | +{int(stress)}"], flush=True)
    for mode in ("every2", "every3", "prop", "flat"):
        r = LG.play(sessions, final, mode, 0.0)
        out["final_pick_changes"][f"target mode {mode} | +0"] = {
            "total_net": r["total_net"], "wallet_steps": r["wallet_steps"], "step_days": r["step_days"],
            "target_days": r["target_days"]}
    (HERE / "explain.json").write_text(json.dumps(out, indent=1, default=int), encoding="utf-8")


if __name__ == "__main__":
    main()
