"""O29f analysis: results.json from _local/results-raw.json (the frozen rule; descriptive tables beside it)."""
from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab  # noqa: E402

RAW = lab.LOCAL / "results-raw.json"


def m(trades, window, days):
    return lab.metrics(trades, lab.O27F.sessions_in(window, days))


def brief(x: dict) -> dict:
    keys = ("sessions", "trades", "net", "net_without_best_day", "dd", "worst_day", "best_day", "win_rate",
            "profit_factor", "green_days", "red_days", "green_weeks", "red_weeks", "green_months", "red_months",
            "stressed", "charges")
    return {k: x[k] for k in keys} | {"monthly": x["monthly"], "exit_reasons": x["exit_reasons"]}


def describe(book: dict) -> list[str]:
    out = []
    for member in book["members"]:
        if member["kind"] == "NAMED":
            out.append(f"{member['name']} [{member['gate']}] exit={member['exit']} vwap={member['vwap_exit']}")
        else:
            g = member["genome"]
            genes = {k: v for k, v in g.items() if k not in ("family", *lab.FIXED_SHARED)}
            out.append(f"{g['family']} [{member['gate']}] {genes}")
    return out


def regime_agreement(manifest: dict) -> dict:
    """Description only: the rebuilt regime (09:20 scan) against the label the live engine logged that day."""
    db = lab.ROOT / "docs/research/fno/2026-10-28-chop-study/_local/dataset/fno-replay.sqlite"
    if not db.is_file():
        return {"available": False}
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    logged: dict = {}
    for day, regime, n in con.execute("SELECT substr(bar_ts,1,10), regime, COUNT(*) FROM fno_signals WHERE regime "
                                      "IS NOT NULL AND regime NOT IN ('', 'UNKNOWN') GROUP BY 1, 2"):
        if n > logged.get(day, ("", 0))[1]:
            logged[day] = (regime, n)
    con.close()
    rebuilt = manifest["rebuilt_regimes_description_only"]
    pairs = [(day, logged[day][0], rebuilt[day]["0920"]) for day in sorted(logged)
             if day in rebuilt]
    same = sum(a == b for _, a, b in pairs)
    crisis = [(d, a, b) for d, a, b in pairs if "CRISIS" in a or "CRISIS" in b]
    return {"available": True, "days": len(pairs), "same": same, "share": round(same / len(pairs), 3) if pairs else None,
            "crisis_days": crisis, "rebuilt_crisis_sessions": sorted(d for d, r in rebuilt.items()
                                                                   if "CRISIS" in (r["0920"] + r["1445"]))}


def main() -> None:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    days, trades, books = raw["days"], raw["trades"], raw["books"]
    manifest = json.loads((lab.YEAR / "manifest.json").read_text(encoding="utf-8"))
    key = lambda b, src="year", w=lab.FULL: lab.task_key(b, src, w)  # noqa: E731
    windows = {"UNSEEN": lab.UNSEEN, "SEEN": ("2026-09-10", "2026-10-28"), "FULL": lab.FULL}

    fixed = {}
    for name, b in lab.FIXED.items():
        fixed[name] = {w: brief(m(trades[key(b)], span, days)) for w, span in windows.items()}
        fixed[name]["describe"] = describe(b)
    nulls = [m(trades[key(b)], lab.UNSEEN, days) for b in lab.null_fixed()]
    null_unseen = sorted(x["net"] for x in nulls)

    seen_archive_days = sorted({t["entry_time"][:10] for b in lab.FIXED.values()
                                for t in trades[key(b, "archive", lab.SEEN)]})
    fidelity = {}
    for name, b in lab.FIXED.items():
        a, y = trades[key(b, "archive", lab.SEEN)], trades[key(b, "year", lab.SEEN)]
        ca = [t for t in a if t.get("net_pnl") is not None]
        cy = [t for t in y if t.get("net_pnl") is not None]
        sa, sy = {(t["bar_ts"], t["direction"]) for t in ca}, {(t["bar_ts"], t["direction"]) for t in cy}
        fidelity[name] = {"archive_trades": len(ca), "candle_trades": len(cy), "same_entries": len(sa & sy),
                          "archive_net": round(sum(t["net_pnl"] for t in ca), 2),
                          "candle_net": round(sum(t["net_pnl"] for t in cy), 2)}

    oos_days = [d for f in lab.FOLDS if f["test"] for d in lab.O27F.sessions_in(f["test"], days)]
    walk = {}
    for track in ("REAL", "NULL"):
        rows, pooled = [], []
        for fold in lab.FOLDS:
            pick = raw["folds"][f"{track}|{fold['name']}"]["pick"]
            b = pick["book"]
            row = {"fold": fold["name"], "pick": pick["digest"], "describe": describe(b),
                   "train": brief(m(trades[key(b)], fold["train"], days)), "plateau": pick["plateau"],
                   "fitness": pick["fitness"]}
            if fold["test"]:
                test = m(trades[key(b)], fold["test"], days)
                row["test"] = brief(test)
                live = m(trades[key(lab.FIXED["UNION_DRIVE"])], fold["test"], days)
                row["union_drive_test"] = {"net": live["net"], "trades": live["trades"], "worst_day": live["worst_day"]}
                test_days = set(lab.O27F.sessions_in(fold["test"], days))
                pooled += [t for t in trades[key(b)] if t["entry_time"][:10] in test_days]
            rows.append(row)
        walk[track] = {"folds": rows, "oos": brief(lab.metrics(pooled, oos_days))}
    live_oos = brief(m(trades[key(lab.FIXED["UNION_DRIVE"])], ("2026-04-01", "2026-10-28"), days))
    real, null = walk["REAL"]["oos"], walk["NULL"]["oos"]
    folds_positive = sum(r["test"]["net"] > 0 for r in walk["REAL"]["folds"] if "test" in r)
    checks = {"oos_net_gt_0": real["net"] > 0, "beats_union_drive": real["net"] > live_oos["net"],
              "beats_null": real["net"] > null["net"], "folds_positive_ge_3": folds_positive >= 3,
              "oos_worst_day_ge_-5000": real["worst_day"] >= -5000}
    final = raw["final_pick"]
    final_row = {"describe": describe(final), "book": final,
                 **{w: brief(m(trades[key(final)], span, days)) for w, span in windows.items()}}

    families = Counter()
    for k, b in books.items():
        if k.startswith("year_2026-01-01_2026-10-28"):
            for member in b["members"]:
                families[member.get("name") or member["genome"]["family"]] += 1
    out = {"schema": "o29f_year_genome_results_v1", "freeze_sha256": raw["freeze_sha256"], "sessions": len(days),
           "first_session": days[0], "last_session": days[-1], "parity": raw["parity"], "fidelity": fidelity,
           "fidelity_days": len(seen_archive_days), "regime_rebuild": regime_agreement(manifest),
           "fixed_books": fixed,
           "null_fixed_unseen": {"count": len(null_unseen), "median": statistics.median(null_unseen),
                                 "positive": sum(v > 0 for v in null_unseen), "best": null_unseen[-1],
                                 "worst": null_unseen[0]},
           "walk_forward": walk, "union_drive_oos": live_oos, "verdict_checks": checks,
           "search_works": all(checks.values()), "final_pick": final_row, "replays": len(trades),
           "memory_pauses": raw["memory_pauses"], "member_usage": dict(families.most_common()),
           "qualification": "NOT_ASSESSED"}
    lab.write_new(HERE / "results.json", out)
    print(json.dumps({"search_works": out["search_works"], "checks": checks, "real_oos": real["net"],
                      "null_oos": null["net"], "union_drive_oos": live_oos["net"]}, indent=1))
    for name, row in fixed.items():
        u, f = row["UNSEEN"], row["FULL"]
        print(f"{name:16} UNSEEN {u['trades']:3}t {u['net']:>10.0f} dd {u['dd']:>7.0f} worst {u['worst_day']:>7.0f} "
              f"| FULL {f['trades']:3}t {f['net']:>10.0f}")


if __name__ == "__main__":
    main()
