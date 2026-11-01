"""Compare every screened book with N07, N04 and N05 on 2024-26. Reads only saved replays. Usage: analyze_screen.py [keys-prefix] [--save name]."""
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
A = HERE.parent / "2026-11-01-fno-failure-anatomy"
YEARS = ("2024", "2025", "2026")
START = 250000.0


def stored(key: str) -> list:
    path = HERE / "_local" / "evals" / f"{key}.json"
    return json.loads(path.read_text(encoding="utf-8"))["trades"]


def closed_dd(trades: list) -> float:
    equity = peak = START
    worst = 0.0
    for t in sorted(trades, key=lambda t: t["exit_time"]):
        equity += t["net_pnl"]
        peak = max(peak, equity)
        worst = max(worst, (peak - equity) / peak)
    return 100 * worst


def weekly(trades: list) -> dict:
    out = defaultdict(float)
    for t in trades:
        iso = date.fromisoformat(t["exit_time"][:10]).isocalendar()
        out[(iso[0], iso[1])] += t["net_pnl"]
    return out


def paired_t(a: list, b: list) -> float:
    wa, wb = weekly(a), weekly(b)
    diff = [wa.get(k, 0.0) - wb.get(k, 0.0) for k in set(wa) | set(wb)]
    diff = [d for d in diff]
    if len(diff) < 3 or statistics.pstdev(diff) == 0:
        return 0.0
    return statistics.mean(diff) / (statistics.stdev(diff) / math.sqrt(len(diff)))


def summary(by_year: dict, base: dict) -> dict:
    allt = [t for y in YEARS for t in by_year[y]]
    losses = [t["net_pnl"] for t in allt if t["net_pnl"] <= 0]
    wins = [t["net_pnl"] for t in allt if t["net_pnl"] > 0]
    days = defaultdict(float)
    for t in allt:
        days[t["entry_time"][:10]] += t["net_pnl"]
    return {"net": {y: round(sum(t["net_pnl"] for t in by_year[y])) for y in YEARS}, "total": round(sum(t["net_pnl"] for t in allt)),
            "delta": {y: round(sum(t["net_pnl"] for t in by_year[y]) - sum(t["net_pnl"] for t in base[y])) for y in YEARS},
            "dd": {y: round(closed_dd(by_year[y]), 2) for y in YEARS}, "worst_dd": round(max(closed_dd(by_year[y]) for y in YEARS), 2),
            "trades": len(allt), "wins": len(wins), "avg_win": round(sum(wins) / max(1, len(wins))), "avg_loss": round(sum(losses) / max(1, len(losses))),
            "worst_trade": round(min(losses, default=0)), "worst_day": round(min(days.values())),
            "t_vs_n07": round(paired_t(allt, [t for y in YEARS for t in base[y]]), 2)}


def main() -> None:
    prefix = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "keys-screen"
    refs = {y: {**json.loads((A / "_local" / f"keys-reference-{y}.json").read_text()), **json.loads((A / "_local" / f"keys-candidate-{y}.json").read_text())} for y in YEARS}
    named = {"N03": "NORMAL|BASE", "N04": "NORMAL|STALL30", "N05": "NORMAL|STRUCT30", "N07": "NORMAL|PREMIUM_STALL"}
    ref_trades = {n: {y: stored(refs[y][k]) for y in YEARS} for n, k in named.items()}
    base = ref_trades["N07"]
    rows = {n: summary(v, base) for n, v in ref_trades.items()}
    keys = {y: json.loads((HERE / "_local" / f"{prefix}-{y}.json").read_text()) for y in YEARS}
    for name in keys["2024"]:
        rows[name] = summary({y: stored(keys[y][name]) for y in YEARS}, base)
    n07 = rows["N07"]
    print(f"{'book':34}{'2024':>8}{'2025':>8}{'2026':>8}{'total':>9}{'+/-':>8}{'d24':>7}{'d25':>7}{'d26':>7}{'DD%':>6}{'n':>4}{'avgW':>6}{'avgL':>7}{'wrstT':>7}{'wrstD':>7}{'t':>6}")
    for name, r in sorted(rows.items(), key=lambda kv: -kv[1]["total"]):
        better = all(r["delta"][y] >= 0 for y in YEARS) and r["worst_dd"] <= n07["worst_dd"] and name not in named
        print(f"{name:34}{r['net']['2024']:>8}{r['net']['2025']:>8}{r['net']['2026']:>8}{r['total']:>9}{r['total'] - n07['total']:>8}{r['delta']['2024']:>7}{r['delta']['2025']:>7}{r['delta']['2026']:>7}{r['worst_dd']:>6}{r['trades']:>4}{r['avg_win']:>6}{r['avg_loss']:>7}{r['worst_trade']:>7}{r['worst_day']:>7}{r['t_vs_n07']:>6}{'  <==' if better else ''}")
    if "--save" in sys.argv:
        (HERE / sys.argv[sys.argv.index("--save") + 1]).write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
