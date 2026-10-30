"""Independent descriptive sensitivity/half-year checks; no strategy fitting."""
import json
from pathlib import Path

import pandas as pd

import diagnose as D


def main():
    p, root = D.HERE, D.ROOT
    diagnosis = D.load(p / "diagnosis.json")
    years, labels, library = {}, {}, {}
    for year in ("2025", "2026"):
        details = D.load(p / f"_local/details-{year}.json")
        rows, trades = details["REF|LIVE"]["days"], details["REF|LIVE"]["trades"]
        years[year] = {"quality_sensitive_splits": {k: D.bucket_comparison(
            [r for r in rows if not r["quality_flag"]], k)
            for k in ("h_small_range", "h_reversing_day", "open_drive", "prev_range_rel")},
                       "half_entry_stretch": {}, "half_prev_range": {}}
        for half, start, end in (
                ("H1", year + "-01-01", year + ("-06-30" if year == "2025" else "-05-31")),
                ("H2", year + ("-07-01" if year == "2025" else "-06-01"), year + "-12-31")):
            years[year]["half_entry_stretch"][half] = {}
            for side in ("NEAR", "STRETCHED"):
                sample = [t for t in trades if start <= t["entry_time"][:10] <= end and t["entry_stretch"] == side]
                years[year]["half_entry_stretch"][half][side] = {
                    "trades": len(sample), "losses": sum(t["net_pnl"] < 0 for t in sample),
                    "net": round(sum(D.norm(t) for t in sample))}
            years[year]["half_prev_range"][half] = D.bucket_comparison(
                [r for r in rows if start <= r["date"] <= end], "prev_range_rel")
        m = diagnosis["years"][year]["books"]["REF|LIVE"]["trade_mechanisms"]
        years[year]["loss_trade_direction_or_stops"] = {
            "underlying_stop": m["by_exit"]["underlying_stop"]["losses"],
            "premium_backstop": m["by_exit"]["premium_backstop"]["losses"],
            "time_stop": m["by_exit"]["time_stop"]["losses"], "total_losing": m["losing_trades"]}
        labels[year] = {r["date"]: "LOSS" if r["net"] < -.005 else "WIN" if r["net"] > .005 else "FLAT" for r in rows}
        raw = D.load(root / f"docs/research/fno/2026-10-30-day-router/_local/results-raw-library-{year}.json")
        library[year] = {}
        for name, key in raw["books"].items():
            ts = [t for t in raw["trades"][key] if t.get("net_pnl") is not None]
            library[year][name] = {
                "on_live_loss_days": sum(D.norm(t) for t in ts if labels[year].get(t["entry_time"][:10]) == "LOSS"),
                "full_net": sum(D.norm(t) for t in ts)}
    families = {}
    for family in ("FADE", "VWAP_REVERT", "RSI2", "PDL_FADE", "TPB"):
        names = [n for n in library["2025"] if D.family(n) == family]
        families[family] = {"variants": len(names),
            "same_variants_positive_on_live_loss_days_both_years": sum(
                all(library[y][n]["on_live_loss_days"] > 0 for y in ("2025", "2026")) for n in names),
            "same_variants_positive_full_book_both_years": sum(
                all(library[y][n]["full_net"] > 0 for y in ("2025", "2026")) for n in names)}
    idx = pd.date_range("2026-01-05 09:15", periods=120, freq="min")
    values = [100 + (i % 11) * .1 + i * .01 for i in range(120)]
    f = pd.DataFrame({"open": values, "high": [v + .2 for v in values], "low": [v - .2 for v in values],
                      "close": values, "volume": [100.] * 120}, index=idx)
    at = pd.Timestamp("2026-01-05 10:06:59")
    before, changed = D.entry_metrics(f, at), f.copy()
    changed.loc[changed.index >= at.floor("min"), ["open", "high", "low", "close", "volume"]] *= 10
    assert D.entry_metrics(changed, at) == before
    counts = D.summarise([{"trades": 1, "net": -10}, {"trades": 1, "net": 20},
                          {"trades": 0, "net": 0}, {"trades": 1, "net": 0}])
    assert (counts["losing_days"], counts["winning_days"], counts["no_trade_days"], counts["flat_active_days"]) == (1, 1, 1, 1)
    out = {"years": years, "matched_family_overlap_HINDSIGHT_ONLY": families,
           "checks": {"completed_bar_future_perturbation": "passed", "no_trade_flat_loss_win_partition": "passed"},
           "diagnosis_sha256": D.sha(p / "diagnosis.json")}
    (p / "crosschecks.json").write_text(json.dumps(out, indent=1, allow_nan=False), encoding="utf-8")
    print("Half-year, quality sensitivity, matched-family and two independent checks complete.")


if __name__ == "__main__":
    main()
