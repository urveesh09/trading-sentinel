"""O29i analysis -> results.json: sideways-day entries per lot, the two-fold check, the random yardstick, and each
family joined to UNION_ADX (the gates never overlap: one book trades a day, never both)."""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-10-29-why-study")]
import analyze_g as AG  # noqa: E402
import lab_i  # noqa: E402

Y = lab_i.Y
H1, H2 = ("2026-01-01", "2026-05-31"), ("2026-06-01", "2026-10-28")


def main() -> None:
    raw = json.loads((lab_i.LOCAL / "results-raw.json").read_text())
    days = json.loads((Y.HERE / "freeze.json").read_text())["bindings"]["year_sessions"]
    trades = {n: raw["trades"][k] for n, k in raw["books"].items()}
    m = {n: {w: AG.per_lot(t, s, days) for w, s in (("FULL", Y.FULL), ("H1", H1), ("H2", H2))}
         for n, t in trades.items()}
    nulls = [n for n in m if n.startswith("NULL")]
    null_med = {w: statistics.median(m[n][w]["net"] for n in nulls) for w in ("FULL", "H1", "H2")}
    families = {}
    for fam in lab_i.SIDE_FAMILIES:
        names = [n for n in m if n.startswith(fam + "|")]
        h1 = max(names, key=lambda n: (m[n]["H1"]["net"], n))
        h2 = max(names, key=lambda n: (m[n]["H2"]["net"], n))
        families[fam] = {"H1_pick": h1, "its_H2": m[h1]["H2"]["net"], "H2_pick": h2, "its_H1": m[h2]["H1"]["net"],
                         "positive_variants_full": sum(m[n]["FULL"]["net"] > 0 for n in names),
                         "variants": len(names),
                         "median_full": statistics.median(m[n]["FULL"]["net"] for n in names)}
        f = families[fam]
        f["helps"] = (f["its_H2"] > 0 and f["its_H1"] > 0 and f["its_H2"] > null_med["H2"]
                      and f["its_H1"] > null_med["H1"])
    combos = {}
    union = trades["UNION_ADX"]
    for fam, f in families.items():
        for pick in {f["H1_pick"], f["H2_pick"]}:
            joined = union + trades[pick]
            combos[f"UNION_ADX+{pick}"] = {"per_lot": AG.per_lot(joined, Y.FULL, days),
                                           "one_lot_weeks": AG.one_lot_weeks(joined, days)}
    out = {"schema": "o29i_results_v1", "freeze_sha256": Y.grid._sha(HERE / "freeze.json"), "metrics_per_lot": m,
           "null_median": null_med, "families": families, "combos": combos,
           "union_adx": {"per_lot": m["UNION_ADX"]["FULL"], "one_lot_weeks": AG.one_lot_weeks(union, days)}}
    Y.write_new(HERE / "results.json", out)
    print("random books on sideways days (median per lot): FULL", null_med["FULL"], "H1", null_med["H1"], "H2", null_med["H2"],
          "| positive", sum(m[n]["FULL"]["net"] > 0 for n in nulls), "of", len(nulls))
    for fam, f in families.items():
        print(f"{fam:12} H1 pick -> H2 {f['its_H2']:>7} | H2 pick -> H1 {f['its_H1']:>7} | positive variants "
              f"{f['positive_variants_full']}/{f['variants']} | median {f['median_full']:>7} | helps {f['helps']}")
    print(f"{'book':55} {'FULL':>7} {'H1':>7} {'H2':>7} {'t':>4} {'worst':>6} {'g/r mo':>6}")
    for n in sorted((n for n in m if not n.startswith("NULL")), key=lambda n: -m[n]["FULL"]["net"])[:14]:
        f = m[n]["FULL"]
        print(f"{n:55} {f['net']:7} {m[n]['H1']['net']:7} {m[n]['H2']['net']:7} {f['trades']:4} {f['worst_day']:6} "
              f"{f['green_months']:2}/{f['red_months']:<2}")
    print("UNION_ADX alone:", {k: out["union_adx"]["per_lot"][k] for k in ("net", "trades", "worst_day", "dd")},
          out["union_adx"]["one_lot_weeks"])
    for n, c in combos.items():
        p = c["per_lot"]
        print(n, {k: p[k] for k in ("net", "trades", "worst_day", "dd", "green_months", "red_months")}, c["one_lot_weeks"])


if __name__ == "__main__":
    main()
