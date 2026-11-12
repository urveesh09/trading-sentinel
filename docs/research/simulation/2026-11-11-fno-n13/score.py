"""Score the frozen N13 arms: leave-one-window-out selection, the final pick and N012-A2's five-check rule."""
import json
from pathlib import Path

from n13_grid import ARMS, CENTER, LINE, distance, neighbours

HERE = Path(__file__).resolve().parent
N12 = HERE.parent / "2026-11-05-fno-n12"
WINDOWS = ("2022", "2023", "2024", "2025", "2026")
GUARD_DAY = 500.0          # an arm may not make any window's worst day more than this worse than N11T's
FLOOR = -2500.0            # no window may lose more than this against N11T


def load():
    control = {w: json.loads((N12 / f"round30-{w}.json").read_bytes())["N11T"] for w in WINDOWS}
    arms = {n: {w: json.loads((HERE / "_local" / w / f"{n}.json").read_bytes()) for w in WINDOWS} for n in LINE}
    return control, arms


def inc(arms, control, name, w):
    return round(arms[name][w]["net"] - control[w]["net"], 2)


def total(arms, control, name, windows=WINDOWS):
    return round(sum(inc(arms, control, name, w) for w in windows), 2)


def guarded(arms, control, name, windows):
    return all(arms[name][w]["unresolved"] == 0 and
               arms[name][w]["worst_day"] >= control[w]["worst_day"] - GUARD_DAY for w in windows)


def pick(arms, control, windows):
    ok = [n for n in LINE if guarded(arms, control, n, windows)]
    return max(ok, key=lambda n: (total(arms, control, n, windows), -distance(n), n))


def after_best_five(arms, control, name):
    diff = {}
    for w in WINDOWS:
        for d in set(arms[name][w]["daily"]) | set(control[w]["daily"]):
            diff[d] = arms[name][w]["daily"].get(d, 0.) - control[w]["daily"].get(d, 0.)
    best = sorted(diff.values(), reverse=True)[:5]
    return round(sum(diff.values()) - sum(v for v in best if v > 0), 2)


def worst(arms, name):
    return min(arms[name][w]["worst_day"] for w in WINDOWS), max(arms[name][w]["drawdown_pct"] for w in WINDOWS)


def main():
    control, arms = load()
    a_total, a_b5 = total(arms, control, CENTER), after_best_five(arms, control, CENTER)
    assert abs(a_total - 4051.45) < 0.02 and abs(a_b5 - 710.38) < 0.02, (a_total, a_b5)   # N012-A as Round 30 scored it
    folds = {}
    for w in WINDOWS:
        chosen = pick(arms, control, [v for v in WINDOWS if v != w])
        folds[w] = {"chosen": chosen, "held_out_increment": inc(arms, control, chosen, w),
                    "n012a_increment": inc(arms, control, CENTER, w)}
    oof = round(sum(f["held_out_increment"] for f in folds.values()), 2)
    final = pick(arms, control, WINDOWS)
    (fw, fd), (aw, ad) = worst(arms, final), worst(arms, CENTER)
    plateau = [total(arms, control, n) for n in neighbours(final)]
    checks = {
        "1_search_beats_fixed_out_of_fold": oof > a_total,
        "2_after_best_five_beats_n012a": after_best_five(arms, control, final) > a_b5,
        "3_worst_day_and_drawdown_no_worse": fw >= aw and fd <= ad + 1e-9,
        "4_no_window_below_floor": all(inc(arms, control, final, w) >= FLOOR for w in WINDOWS),
        "5_plateau_neighbours_positive": sum(plateau) / len(plateau) > 0,
    }
    table = {n: {"total": total(arms, control, n), **{w: inc(arms, control, n, w) for w in WINDOWS},
                 "after_best_five": after_best_five(arms, control, n), "worst_day": worst(arms, n)[0],
                 "max_drawdown_pct": worst(arms, n)[1], "guarded": guarded(arms, control, n, WINDOWS),
                 "trades": sum(arms[n][w]["closed"] for w in WINDOWS),
                 "lock_exits": sum(arms[n][w]["exit_reasons"].get("profit_lock", 0) for w in WINDOWS)}
             for n in LINE}
    result = {"n012a": {"name": CENTER, "total": a_total, "after_best_five": a_b5, "worst_day": aw,
                        "max_drawdown_pct": ad},
              "folds": folds, "out_of_fold_total": oof,
              "final_pick": {"name": final, "total": total(arms, control, final),
                             "after_best_five": after_best_five(arms, control, final), "worst_day": fw,
                             "max_drawdown_pct": fd, "neighbour_totals": plateau},
              "checks": checks, "adopt": final != CENTER and all(checks.values()), "arms": table}
    (HERE / "results.json").write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("n012a", "folds", "out_of_fold_total", "final_pick", "checks", "adopt")},
                     indent=1))
    print(json.dumps(table, indent=1))


if __name__ == "__main__":
    main()
