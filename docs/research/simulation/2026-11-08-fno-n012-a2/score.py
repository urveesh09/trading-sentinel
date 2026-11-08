"""Score the frozen N012-A2 grid: leave-one-window-out selection, the final pick and the frozen decision rule."""
import json
from pathlib import Path

from n012a2_grid import ARMS, CENTER, S_GRID, A_GRID, T_GRID, arm_name

HERE = Path(__file__).resolve().parent
N12 = HERE.parent / "2026-11-05-fno-n12"
WINDOWS = ("2022", "2023", "2024", "2025", "2026")
GUARD_DAY = 500.0          # an arm may not make any window's worst day more than this worse than N11T's
FLOOR = -2500.0            # no window may lose more than this against N11T
A_NAME = arm_name(*CENTER)


def load():
    control = {w: json.loads((N12 / f"round30-{w}.json").read_bytes())["N11T"] for w in WINDOWS}
    arms = {}
    for name in ARMS:
        arms[name] = {w: json.loads((HERE / "_local" / w / f"{name}.json").read_bytes()) for w in WINDOWS}
    return control, arms


def inc(arms, control, name, w):
    return round(arms[name][w]["net"] - control[w]["net"], 2)


def guarded(arms, control, name, windows):
    return all(arms[name][w]["unresolved"] == 0 and
               arms[name][w]["worst_day"] >= control[w]["worst_day"] - GUARD_DAY for w in windows)


def distance(name):
    s, a, t = ARMS[name]
    grid = lambda g, v: g.index(v)
    return (abs(grid(S_GRID, s) - 1) + abs(grid(A_GRID, a) - 1) + abs(grid(T_GRID, t) - 1))


def pick(arms, control, windows):
    ok = [n for n in ARMS if guarded(arms, control, n, windows)]
    return max(ok, key=lambda n: (round(sum(inc(arms, control, n, w) for w in windows), 2), -distance(n), n))


def after_best_five(arms, control, name):
    diff = {}
    for w in WINDOWS:
        days = set(arms[name][w]["daily"]) | set(control[w]["daily"])
        for d in days:
            diff[d] = arms[name][w]["daily"].get(d, 0.) - control[w]["daily"].get(d, 0.)
    best = sorted(diff.values(), reverse=True)[:5]
    return round(sum(diff.values()) - sum(v for v in best if v > 0), 2)


def neighbours(name):
    s, a, t = ARMS[name]
    out = []
    for grid, i in ((S_GRID, 0), (A_GRID, 1), (T_GRID, 2)):
        k = grid.index((s, a, t)[i])
        for j in (k - 1, k + 1):
            if 0 <= j < len(grid):
                key = [s, a, t]
                key[i] = grid[j]
                out.append(arm_name(*key))
    return out


def worst(arms, name):
    return min(arms[name][w]["worst_day"] for w in WINDOWS), max(arms[name][w]["drawdown_pct"] for w in WINDOWS)


def main():
    control, arms = load()
    a_total = round(sum(inc(arms, control, A_NAME, w) for w in WINDOWS), 2)
    assert abs(a_total - 4051.45) < 0.02, a_total               # N012-A as Round 30 scored it
    a_b5 = after_best_five(arms, control, A_NAME)
    assert abs(a_b5 - 710.38) < 0.02, a_b5
    folds = {}
    for w in WINDOWS:
        rest = [v for v in WINDOWS if v != w]
        chosen = pick(arms, control, rest)
        folds[w] = {"chosen": chosen, "held_out_increment": inc(arms, control, chosen, w),
                    "n012a_increment": inc(arms, control, A_NAME, w)}
    oof = round(sum(f["held_out_increment"] for f in folds.values()), 2)
    final = pick(arms, control, WINDOWS)
    f_total = round(sum(inc(arms, control, final, w) for w in WINDOWS), 2)
    f_b5 = after_best_five(arms, control, final)
    (fw, fd), (aw, ad) = worst(arms, final), worst(arms, A_NAME)
    plateau = [inc_sum for inc_sum in (sum(inc(arms, control, n, w) for w in WINDOWS) for n in neighbours(final))]
    checks = {
        "1_search_beats_fixed_out_of_fold": oof > a_total,
        "2_after_best_five_beats_n012a": f_b5 > a_b5,
        "3_worst_day_and_drawdown_no_worse": fw >= aw and fd <= ad + 1e-9,
        "4_no_window_below_floor": all(inc(arms, control, final, w) >= FLOOR for w in WINDOWS),
        "5_plateau_neighbours_positive": sum(plateau) / len(plateau) > 0,
    }
    table = {n: {"total": round(sum(inc(arms, control, n, w) for w in WINDOWS), 2),
                 **{w: inc(arms, control, n, w) for w in WINDOWS},
                 "after_best_five": after_best_five(arms, control, n),
                 "worst_day": worst(arms, n)[0], "max_drawdown_pct": worst(arms, n)[1],
                 "guarded": guarded(arms, control, n, WINDOWS)}
             for n in ARMS}
    result = {"n012a": {"name": A_NAME, "total": a_total, "after_best_five": a_b5, "worst_day": aw,
                        "max_drawdown_pct": ad},
              "folds": folds, "out_of_fold_total": oof,
              "final_pick": {"name": final, "total": f_total, "after_best_five": f_b5, "worst_day": fw,
                             "max_drawdown_pct": fd, "neighbour_totals": [round(p, 2) for p in plateau]},
              "checks": checks, "adopt_a2": final != A_NAME and all(checks.values()), "arms": table}
    (HERE / "results.json").write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("n012a", "folds", "out_of_fold_total", "final_pick", "checks",
                                             "adopt_a2")}, indent=1))


if __name__ == "__main__":
    main()
