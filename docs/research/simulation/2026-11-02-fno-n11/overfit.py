"""The honest checks, from saved replays only: placebos, persistence, trading smaller, parts by year, 50 other strategies, the random-entry control. Writes overfit.json.
Changes no book and no verdict. The overfitting estimate itself is in pbo.py."""
from __future__ import annotations

import bisect
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n11_rules as R  # noqa: E402
import stress as ST  # noqa: E402

SIM = HERE.parent
LOCAL = HERE / "_local"
N09 = SIM / "2026-11-01-fno-n09" / "_local"
YEARS = ST.YEARS
RATIO, NEED = ST.RATIO, ST.NEED
VOL = ST.vol_table()


def vol_flag(day: str, ratio: float = RATIO) -> bool:
    atr, usual = VOL.get(day, (None, None))
    return bool(atr is not None and usual is not None and atr >= usual * ratio)


def trades(phase: str, y: str, name: str) -> list:
    key = json.loads((LOCAL / f"keys-{phase}-{y}.json").read_text(encoding="utf-8"))[name]
    return json.loads((LOCAL / "evals" / f"{key}.json").read_text(encoding="utf-8"))["trades"]


def stream() -> list:
    rows = []
    for y in YEARS:
        key = json.loads((N09 / f"keys-diag-{y}.json").read_text(encoding="utf-8"))["DIAG"]
        for t in json.loads((N09 / f"evals-{y}" / f"{key}.json").read_text(encoding="utf-8"))["trades"]:
            rows.append({**t, "_y": y})
    return sorted(rows, key=lambda t: t["entry_time"])


def mask_of(rows: list, ratio: float = RATIO, need: int = NEED) -> list:
    exits = sorted((t["exit_time"], float(t["net_pnl"])) for t in rows)
    at = [e[0] for e in exits]
    nets = [e[1] for e in exits]
    return [R.stand_aside(vol_flag(t["entry_time"][:10], ratio), nets[:bisect.bisect_left(at, t["entry_time"])], need) for t in rows]


def placebos(rows: list) -> dict:
    mask = mask_of(rows)
    nets = np.array([float(t["net_pnl"]) for t in rows])
    actual = float(-nets[np.array(mask)].sum())
    count = int(sum(mask))
    known = []
    exits = sorted(t["exit_time"] for t in rows)
    for i, t in enumerate(rows):
        if not vol_flag(t["entry_time"][:10]) and bisect.bisect_left(exits, t["entry_time"]) >= NEED:
            known.append(i)
    rng = random.Random(11)
    draws = sorted(float(-nets[rng.sample(known, count)].sum()) for _ in range(20000))
    flags = np.array(mask)
    rotated = sorted(float(-nets[np.roll(flags, s)].sum()) for s in range(1, len(rows)))
    by_year = {y: {"skipped": sum(m and t["_y"] == y for t, m in zip(rows, mask)), "one_lot_net_skipped": round(sum(float(t["net_pnl"]) for t, m in zip(rows, mask) if m and t["_y"] == y)),
                   "one_lot_net_kept": round(sum(float(t["net_pnl"]) for t, m in zip(rows, mask) if not m and t["_y"] == y))} for y in YEARS}
    p = sum(g >= actual for g in rotated) / len(rotated)
    return {"skipped": count, "gain_one_lot": round(actual), "by_year": by_year,
            "same_count_at_random": {"median": round(draws[10000]), "p95": round(draws[19000]), "share_at_or_above_actual": sum(d >= actual for d in draws) / 20000},
            "state_rotated_through_time": {"shifts": len(rotated), "median": round(rotated[len(rotated) // 2]), "max": round(rotated[-1]), "share_at_or_above_actual": round(p, 4)},
            "check_13_rotated_p_at_most_0_10": p <= 0.10}


def persistence(rows: list) -> dict:
    """Is the paper record persistent at all? Each 20-trade sum against the next 20, by exit order, windows not overlapping within a pair."""
    ordered = sorted(rows, key=lambda t: t["exit_time"])
    nets = np.array([float(t["net_pnl"]) for t in ordered])
    years = [t["_y"] for t in ordered]

    def corr(keep) -> dict:
        xs, ys = [], []
        for i in range(20, len(nets) - 19):
            if keep(years[i - 20]) and keep(years[i + 19]):
                xs.append(nets[i - 20:i].sum())
                ys.append(nets[i:i + 20].sum())
        x, y = np.array(xs), np.array(ys)
        negative = x <= 0
        return {"pairs": len(x), "correlation": round(float(np.corrcoef(x, y)[0, 1]), 3), "next_20_mean_after_a_losing_20": round(float(y[negative].mean())) if negative.any() else None,
                "next_20_mean_after_a_winning_20": round(float(y[~negative].mean())) if (~negative).any() else None, "share_of_losing_windows": round(float(negative.mean()), 3)}

    return {"all_four_years": corr(lambda y: True), "without_2023": corr(lambda y: y != "2023"),
            "note": "Overlapping windows, so these correlations overstate how much independent evidence there is. Read the sign and the size, not a significance."}


def trading_smaller() -> dict:
    """Would trading smaller all the time do as well? N10 retry, every rupee scaled down so its worst annual fall equals N11's. Arithmetic, not a replay: lots don't come in fractions."""
    def fall(rows):
        eq = pk = 250000.0
        worst = 0.0
        for t in sorted(rows, key=lambda r: r["exit_time"]):
            eq += float(t["net_pnl"])
            pk = max(pk, eq)
            worst = max(worst, (pk - eq) / pk)
        return worst * 100

    n11 = {y: trades("panel", y, "N11") for y in YEARS}
    n10 = {y: trades("controls", y, "N10") for y in YEARS}
    f11, f10 = max(fall(n11[y]) for y in YEARS), max(fall(n10[y]) for y in YEARS)
    s11, s10 = sum(float(t["net_pnl"]) for y in YEARS for t in n11[y]), sum(float(t["net_pnl"]) for y in YEARS for t in n10[y])
    scale = f11 / f10
    return {"n11_sum": round(s11), "n11_fall": round(f11, 2), "n10_retry_sum": round(s10), "n10_retry_fall": round(f10, 2), "scale": round(scale, 3), "n10_retry_scaled_sum": round(s10 * scale), "n11_beats_trading_smaller": s11 > s10 * scale,
            "without_2023": {"n11": round(s11 - sum(float(t["net_pnl"]) for t in n11["2023"])), "n10_retry": round(s10 - sum(float(t["net_pnl"]) for t in n10["2023"]))}}


def parts() -> dict:
    names = ("N11", "NO_STAND", "NO_LOSS", "NO_ADD", "NO_VOL")
    table = {n: {y: round(sum(float(t["net_pnl"]) for t in trades("panel", y, n))) for y in YEARS} for n in names}
    return {"net": table, "what_each_part_adds": {n.replace("NO_", ""): {y: table["N11"][y] - table[n][y] for y in YEARS} for n in names[1:]}}


def others(rows_n08_len: int = 0) -> dict:
    """The rule on 50 other strategies, each read against its own paper record. They share the market, so this isn't independent data."""
    supp = {y: json.loads((N09 / f"keys-supp-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
    broad = {y: json.loads((SIM / f"2026-10-31-fno-broad-search/_local/keys-screen-{y}.json").read_text(encoding="utf-8")) for y in YEARS[1:]}
    gap = {y: json.loads((SIM / f"2026-10-31-fno-complements/_local/keys-{y}.json").read_text(encoding="utf-8")) for y in YEARS[1:]}
    gains = defaultdict(list)
    skipped = defaultdict(lambda: [0, 0.0])
    kept = defaultdict(lambda: [0, 0.0])
    names = [n for n in supp["2023"] if n.startswith("RAW|")]
    for name in names:
        rows = [{**t, "_y": "2023"} for t in json.loads((N09 / "evals-2023" / f"{supp['2023'][name]}.json").read_text(encoding="utf-8"))["trades"]]
        for y in YEARS[1:]:
            source, folder = (broad[y], SIM / "2026-10-31-fno-broad-search/_local/evals") if name in broad[y] else (gap[y], SIM / "2026-10-31-fno-complements/_local/evals")
            rows += [{**t, "_y": y} for t in json.loads((folder / f"{source[name]}.json").read_text(encoding="utf-8"))["trades"]]
        rows = sorted((t for t in rows if t.get("net_pnl") is not None), key=lambda t: t["entry_time"])
        per = defaultdict(float)
        for t, m in zip(rows, mask_of(rows)):
            cell = skipped if m else kept
            cell[t["_y"]][0] += 1
            cell[t["_y"]][1] += float(t["net_pnl"])
            if m:
                per[t["_y"]] -= float(t["net_pnl"])
        for y in YEARS:
            gains[y].append(per[y])
    table = {}
    for y in YEARS:
        g = np.array(gains[y])
        table[y] = {"helped": int((g > 0).sum()), "hurt": int((g < 0).sum()), "same": int((g == 0).sum()), "median_gain": round(float(np.median(g))), "mean_per_skipped_trade": round(skipped[y][1] / max(1, skipped[y][0])), "mean_per_kept_trade": round(kept[y][1] / max(1, kept[y][0])), "skipped": skipped[y][0]}
    total = sum(np.array(gains[y]) for y in YEARS)
    later = sum(np.array(gains[y]) for y in YEARS[1:])
    return {"books": len(names), "by_year": table, "four_years": {"helped": int((total > 0).sum()), "hurt": int((total < 0).sum()), "median_gain": round(float(np.median(total)))},
            "without_2023": {"helped": int((later > 0).sum()), "hurt": int((later < 0).sum()), "median_gain": round(float(np.median(later)))},
            "reading": "Most of these books lose, so standing aside saves money on them whatever the state means. The mean per skipped trade against the mean per kept trade is the fair reading: is the state marking worse trades?"}


def randoms() -> dict:
    out = {}
    if not all((LOCAL / f"keys-random-{y}.json").exists() for y in YEARS):
        return {"status": "not finished"}
    for tag in ("ADD", "STAND"):
        out[tag] = {}
        for y in YEARS:
            diffs = []
            for i in range(10):
                base = sum(float(t["net_pnl"]) for t in trades("random", y, f"RANDOM|{i:02d}|BASE"))
                other = sum(float(t["net_pnl"]) for t in trades("random", y, f"RANDOM|{i:02d}|{tag}"))
                diffs.append(other - base)
            out[tag][y] = {"helped": sum(d > 0 for d in diffs), "hurt": sum(d < 0 for d in diffs), "median_change": round(float(np.median(diffs)))}
    return out


def main() -> None:
    rows = stream()
    result = {"note": "All data seen. Descriptive, from saved replays.", "placebos": placebos(rows), "persistence": persistence(rows), "trading_smaller": trading_smaller(), "parts_by_year": parts(), "others": others(), "random_entries": randoms()}
    (HERE / "overfit.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
