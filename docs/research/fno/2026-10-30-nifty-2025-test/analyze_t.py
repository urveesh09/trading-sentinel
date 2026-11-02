"""O30 analysis -> results.json: the frozen books on NIFTY 2025 per lot, the frozen verdicts, and 2025 + 2026 together.

Written and frozen before any 2025 replay. 2026 comes from the stored O29f / O29g / O29i replays (one file per book,
looked up by the book's digest), never re-scored.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_t as T  # noqa: E402

Y, G = T.Y, T.G
sys.path.insert(0, str(T.ROOT / "docs/research/fno/2026-10-29-why-study"))
import analyze_g as AG  # noqa: E402

FULL26 = ("2026-01-01", "2026-10-28")
WINDOWS = {"FULL": T.WINDOW, "H1": ("2025-01-01", "2025-06-30"), "H2": ("2025-07-01", "2025-12-31"),
           "Q1": ("2025-01-01", "2025-03-31"), "Q2": ("2025-04-01", "2025-06-30"),
           "Q3": ("2025-07-01", "2025-09-30"), "Q4": ("2025-10-01", "2025-12-31")}
STORED = [T.ROOT / f"docs/research/fno/{s}/_local/evals" for s in
          ("2026-10-29-sideways-study", "2026-10-29-why-study", "2026-10-29-year-genome")]
KEY_BOOKS = ("UNION_ADX", "UNION", "UNION_DRIVE", "TPB|adx_abs20:HIGH", "TPB|ALWAYS",
             *T.SIDE_PICKS.values())


def stored_2026(book: dict) -> list:
    name = f"year_{FULL26[0]}_{FULL26[1]}_{Y.digest(book)}.json"
    for folder in STORED:
        if (folder / name).is_file():
            return json.loads((folder / name).read_text(encoding="utf-8"))["trades"]
    raise SystemExit(f"no stored 2026 replay for {book}")


def main() -> None:
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    raw = json.loads((T.LOCAL / "results-raw.json").read_text(encoding="utf-8"))
    assert raw["freeze_sha256"] == Y.grid._sha(HERE / "freeze.json")
    days = frozen["bindings"]["sessions"]
    days26 = json.loads(T.FREEZES["o29f"].read_text(encoding="utf-8"))["bindings"]["year_sessions"]
    trades = {n: raw["trades"][k] for n, k in raw["books"].items()}
    m = {n: {w: AG.per_lot(t, span, days) for w, span in WINDOWS.items()} for n, t in trades.items()}

    def null_median(suffix: str) -> float:
        return statistics.median(m[f"NULL{i:02d}|{suffix}"]["FULL"]["net"] for i in range(20))
    nulls = {s: null_median(s) for s in ("ALWAYS", "adx_abs25:HIGH", "sideways")}
    net = {n: m[n]["FULL"]["net"] for n in m}
    pick = T.SIDE_PICKS
    combos = {}
    for label in pick:
        joined = trades["UNION_ADX"] + trades[pick[label]]
        combos[f"UNION_ADX+{label}"] = {"per_lot": AG.per_lot(joined, T.WINDOW, days),
                                        "one_lot_weeks": AG.one_lot_weeks(joined, days)}
    verdicts = {
        "trend_book_holds": net["UNION_ADX"] > 0 and net["UNION_ADX"] > net["UNION"]
        and net["UNION_ADX"] > net["UNION_DRIVE"] and net["UNION_ADX"] > nulls["adx_abs25:HIGH"],
        "fade_holds": net[pick["FADE_MAIN"]] > 0 and net[pick["FADE_MAIN"]] > nulls["sideways"],
        "pdl_holds": net[pick["PDL_MAIN"]] > 0 and net[pick["PDL_MAIN"]] > nulls["sideways"],
        "tpb20_holds": net["TPB|adx_abs20:HIGH"] > 0 and net["TPB|adx_abs20:HIGH"] > net["TPB|ALWAYS"],
    }
    verdicts["add_fade_recommendable"] = verdicts["fade_holds"] and (
        combos["UNION_ADX+FADE_MAIN"]["per_lot"]["net"] > net["UNION_ADX"])

    # the ADX gate's 2025 calendar: how many sessions had a reading and how many were trend days
    table = T.table("year")
    sides = [table.get(d, {}).get("side", {}).get("adx_abs25") for d in days]
    gate = {"sessions": len(days), "with_reading": sum(s is not None for s in sides),
            "adx25_high": sum(s == "HIGH" for s in sides), "adx25_low": sum(s == "LOW" for s in sides)}
    gate["high_by_month"] = {}
    for d, s in zip(days, sides):
        gate["high_by_month"].setdefault(d[:7], 0)
        gate["high_by_month"][d[:7]] += s == "HIGH"

    both = {}
    for n in KEY_BOOKS:
        t26 = stored_2026(frozen["books"][n])
        both[n] = {"2026": AG.per_lot(t26, FULL26, days26),
                   "both": AG.per_lot(trades[n] + t26, (T.WINDOW[0], FULL26[1]), days + days26),
                   "both_one_lot_weeks": AG.one_lot_weeks(trades[n] + t26, days + days26)}
    for label in ("FADE_MAIN", "PDL_MAIN"):
        t26 = stored_2026(frozen["books"]["UNION_ADX"]) + stored_2026(frozen["books"][pick[label]])
        joined = trades["UNION_ADX"] + trades[pick[label]] + t26
        both[f"UNION_ADX+{label}"] = {"2026": AG.per_lot(t26, FULL26, days26),
                                      "both": AG.per_lot(joined, (T.WINDOW[0], FULL26[1]), days + days26),
                                      "both_one_lot_weeks": AG.one_lot_weeks(joined, days + days26)}

    weeks = {n: AG.one_lot_weeks(trades[n], days) for n in KEY_BOOKS}
    out = {"schema": "o30_results_v1", "freeze_sha256": raw["freeze_sha256"], "rule": frozen["rule"],
           "verdicts": verdicts, "null_median_2025": nulls, "adx_gate_2025": gate, "metrics_per_lot_2025": m,
           "combos_2025": combos, "one_lot_weeks_2025": weeks, "both_years": both,
           "memory_pauses": raw.get("memory_pauses")}
    Y.write_new(HERE / "results.json", out)

    print("verdicts:", verdicts)
    print("random books, median per lot 2025:", nulls)
    print("ADX gate 2025:", {k: v for k, v in gate.items() if k != "high_by_month"}, gate["high_by_month"])
    print(f"{'book (2025, per lot)':52} {'net':>7} {'H1':>7} {'H2':>7} {'t':>4} {'worst':>6} {'dd':>6} {'g/r mo':>6}")
    for n in sorted((n for n in m if not n.startswith("NULL")), key=lambda n: -net[n]):
        f = m[n]["FULL"]
        print(f"{n:52} {f['net']:7} {m[n]['H1']['net']:7} {m[n]['H2']['net']:7} {f['trades']:4} {f['worst_day']:6} "
              f"{f['dd']:6} {f['green_months']:2}/{f['red_months']:<2}")
    for n, c in combos.items():
        p = c["per_lot"]
        print(n, {k: p[k] for k in ("net", "trades", "worst_day", "dd", "green_months", "red_months")}, c["one_lot_weeks"])
    print("one-lot weeks 2025:", json.dumps(weeks))
    for n, b in both.items():
        p = b["both"]
        print(f"BOTH {n:48} 2026 {b['2026']['net']:7} | 2025+2026 {p['net']:7} t {p['trades']:4} worst {p['worst_day']:6} "
              f"dd {p['dd']:6} months {p['green_months']}/{p['red_months']} weeks {b['both_one_lot_weeks']}")
    print("UNION_ADX by month 2025:", m["UNION_ADX"]["FULL"]["monthly"])


if __name__ == "__main__":
    main()
