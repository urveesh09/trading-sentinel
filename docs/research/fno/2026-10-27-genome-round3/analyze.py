"""O27f: turn _local/results-raw.json into results.json and the README tables. Read-only over the raw run."""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab  # noqa: E402

RAW = json.loads((lab.LOCAL / "results-raw.json").read_text(encoding="utf-8"))
DAYS = RAW["days"]
TRADES = RAW["trades"]
# The parity arm ran outside the search pool; its replay is on disk (the gate compared it with the shipped book).
TRADES["PASSTHROUGH"] = json.loads((lab.EVALS / "PASSTHROUGH.json").read_text(encoding="utf-8"))["trades"]
GENOMES = RAW["genomes"]
FOLDS = RAW["folds"]
TESTS = [f for f in lab.FOLDS if f["test"]]
OOS_DAYS = [d for f in TESTS for d in lab.sessions_in(f["test"], DAYS)]


def lot_size() -> int:
    sizes = Counter(int(t["entry_qty"]) // int(t["lots_at_exit"]) for t in TRADES["PASSTHROUGH"]
                    if t.get("entry_qty") and t.get("lots_at_exit") and not t.get("fills"))
    return sizes.most_common(1)[0][0]


LOT = lot_size()
REFS = {}
for name, trades in RAW["references"].items():
    fixed = []
    for t in trades:
        t = dict(t)
        if not t.get("entry_qty") and t.get("lots_at_exit"):
            t["entry_qty"] = int(t["lots_at_exit"]) * LOT
        fixed.append(t)
    REFS[name] = fixed
REFS["SHIPPED"] = TRADES["PASSTHROUGH"]


def m(trades, window_or_days):
    days = window_or_days if isinstance(window_or_days, list) else lab.sessions_in(window_or_days, DAYS)
    return lab.metrics(trades, days)


def short(g: dict) -> str:
    if g is None:
        return "-"
    fam = {k: g[k] for k in lab.FAMILY_GENES[g["family"]]}
    if "en_members" in fam:
        fam["en_members"] = "+".join(fam["en_members"])
    shared = {k: g[k] for k in lab.SHARED_GENES if g[k] != lab.SHIPPED_SHARED[k]}
    body = ", ".join(f"{k}={v}" for k, v in {**fam, **shared}.items())
    return f"{g['family']}({body})" + (" FLIPPED" if g.get("flip") else "")


def row(trades, days) -> dict:
    x = m(trades, days)
    return {k: x[k] for k in ("sessions", "trades", "unresolved", "net", "net_without_best_day", "dd", "stressed",
                              "win_rate", "profit_factor", "green_days", "red_days", "worst_day", "weeks",
                              "green_weeks", "red_weeks", "charges")} | {"daily": x["daily"],
                                                                        "exit_reasons": x["exit_reasons"]}


def walk_forward(track: str) -> dict:
    folds, oos_trades = [], []
    for f in TESTS:
        pick = FOLDS[f"{track}|{f['name']}"]["pick"]
        name = pick["digest"]
        test = row(TRADES[name], f["test"])
        folds.append({"fold": f["name"], "train_window": f["train"], "test_window": f["test"], "pick": pick["genome"],
                      "digest": name, "train_fitness": pick["fitness"], "plateau": pick["plateau"],
                      "train": row(TRADES[name], f["train"]), "test_result": test,
                      "evaluated_by_fold": len(FOLDS[f"{track}|{f['name']}"]["seen"])})
        oos_trades += [t for t in TRADES[name] if t["entry_time"][:10] in set(lab.sessions_in(f["test"], DAYS))]
    oos = row(oos_trades, OOS_DAYS)
    return {"folds": folds, "oos": oos, "positive_folds": sum(x["test_result"]["net"] > 0 for x in folds)}


def family_of(name):
    g = GENOMES.get(name)
    return g["family"] if g else None


def pool_names(track):
    return [lab.digest(g) for g in lab.pool(track)]


def family_tables():
    out = {}
    for family in (*lab.REAL_FAMILIES, "NULL_RANDOM"):
        names = [n for n in pool_names("NULL" if family == "NULL_RANDOM" else "REAL") if family_of(n) == family]
        fits_a = [lab.fitness(m(TRADES[n], lab.A)) for n in names]
        full = [m(TRADES[n], lab.FULL) for n in names]
        best = max(names, key=lambda n: (lab.fitness(m(TRADES[n], lab.A)), n))
        # Family-restricted walk-forward on the pool alone: best training fitness, scored on the next block.
        wf = []
        for f in TESTS:
            pick = max(names, key=lambda n: (lab.fitness(m(TRADES[n], f["train"])), n))
            wf.append(m(TRADES[pick], f["test"])["net"])
        out[family] = {
            "pool": len(names),
            "full_net_positive_share": round(sum(x["net"] > 0 for x in full) / len(full), 3),
            "full_net_median": round(statistics.median(x["net"] for x in full), 2),
            "full_trades_median": statistics.median(x["trades"] for x in full),
            "A_fitness_p50": round(statistics.median(fits_a), 3),
            "A_fitness_p90": round(sorted(fits_a)[int(0.9 * (len(fits_a) - 1))], 3),
            "A_fitness_best": round(max(fits_a), 3),
            "best_on_A": {"genome": GENOMES[best], "A": row(TRADES[best], lab.A), "B": row(TRADES[best], lab.B)},
            "pool_walk_forward_test_nets": wf, "pool_walk_forward_total": round(sum(wf), 2)}
    return out


def allele_effects():
    """Main effects over the uniformly sampled REAL pool (seeds excluded): mean FULL net and the share of genomes
    with positive FULL net, per allele. Descriptive, seen data."""
    seeded = {lab.digest(g) for g in lab.seeds()}
    names = [n for n in pool_names("REAL") if n not in seeded]
    rows = {}
    for gene, alleles in lab.SHARED_GENES.items():
        rows[gene] = {}
        for allele in alleles:
            hits = [n for n in names if GENOMES[n][gene] == allele]
            res = [m(TRADES[n], lab.FULL) for n in hits]
            rows[gene][str(allele)] = {"n": len(hits), "mean_net": round(statistics.mean(r["net"] for r in res), 1),
                                       "positive_share": round(sum(r["net"] > 0 for r in res) / len(res), 3),
                                       "mean_trades": round(statistics.mean(r["trades"] for r in res), 1)}
    return rows


def top_k_generalisation(k=10):
    """Mean B result of the k best A-fitness pool genomes, REAL against NULL (does A rank carry to B at all?)."""
    out = {}
    for track in ("REAL", "NULL"):
        names = sorted(pool_names(track), key=lambda n: (lab.fitness(m(TRADES[n], lab.A)), n), reverse=True)[:k]
        bs = [m(TRADES[n], lab.B)["net"] for n in names]
        out[track] = {"mean_B_net": round(statistics.mean(bs), 2), "positive_B": sum(b > 0 for b in bs), "k": k}
    # Rank correlation between A fitness and B net across the REAL pool.
    names = pool_names("REAL")
    a = [lab.fitness(m(TRADES[n], lab.A)) for n in names]
    b = [m(TRADES[n], lab.B)["net"] for n in names]
    out["REAL_spearman_A_fitness_vs_B_net"] = round(_spearman(a, b), 3)
    return out


def _spearman(x, y):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    rx, ry = ranks(x), ranks(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sx = sum((a - mx) ** 2 for a in rx) ** 0.5
    sy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (sx * sy) if sx and sy else 0.0


def persistence():
    """Does a genome's result in one period predict the next? Spearman of net across the REAL pool between
    consecutive calendar weeks (genomes trading in both weeks), and between A and B."""
    from datetime import date
    names = pool_names("REAL")
    weeks: dict = {}
    for d in DAYS:
        weeks.setdefault(date.fromisoformat(d).isocalendar()[:2], []).append(d)
    keys = sorted(weeks)
    pairs = []
    for w1, w2 in zip(keys, keys[1:]):
        a, b = [], []
        for n in names:
            m1, m2 = m(TRADES[n], weeks[w1]), m(TRADES[n], weeks[w2])
            if m1["trades"] and m2["trades"]:
                a.append(m1["net"])
                b.append(m2["net"])
        pairs.append({"from": weeks[w1][0], "to": weeks[w2][0], "genomes": len(a),
                      "spearman": round(_spearman(a, b), 3) if len(a) >= 10 else None})
    a, b = [], []
    for n in names:
        ma, mb = m(TRADES[n], lab.A), m(TRADES[n], lab.B)
        if ma["trades"] >= 4 and mb["trades"] >= 3:
            a.append(ma["net"])
            b.append(mb["net"])
    same_sign = sum((x > 0) == (y > 0) for x, y in zip(a, b))
    return {"weekly": pairs, "A_vs_B": {"genomes": len(a), "spearman": round(_spearman(a, b), 3),
                                        "same_sign": same_sign},
            "mean_weekly_spearman": round(statistics.mean(p["spearman"] for p in pairs if p["spearman"] is not None), 3)}


def final_profile():
    pick = FOLDS["REAL|FINAL"]["pick"]
    name = pick["digest"]
    near = lab.neighbours(pick["genome"])
    near_full = [m(TRADES[lab.digest(n)], lab.FULL) for n in near if lab.digest(n) in TRADES]
    return {"pick": pick, "short": short(pick["genome"]), "FULL": row(TRADES[name], lab.FULL),
            "A": row(TRADES[name], lab.A), "B": row(TRADES[name], lab.B),
            "neighbours": {"count": len(near_full), "positive_full_net": sum(x["net"] > 0 for x in near_full),
                           "median_full_net": round(statistics.median(x["net"] for x in near_full), 2),
                           "min_full_net": round(min(x["net"] for x in near_full), 2)},
            "flipped": row(TRADES[RAW["flip_digest"]], lab.FULL),
            "top5": [{"short": short(r["genome"]), "fitness": r["fitness"], "plateau": r["plateau"],
                      "FULL": {k: v for k, v in row(TRADES[r["digest"]], lab.FULL).items() if k != "daily"}}
                     for r in FOLDS["REAL|FINAL"]["top"]]}


def main():
    real, null = walk_forward("REAL"), walk_forward("NULL")
    refs_oos = {name: row(trades, OOS_DAYS) for name, trades in REFS.items()}
    shipped = refs_oos["SHIPPED"]
    verdict = {"oos_positive": real["oos"]["net"] > 0, "beats_shipped": real["oos"]["net"] > shipped["net"],
               "beats_null": real["oos"]["net"] > null["oos"]["net"], "folds_positive_ge_2": real["positive_folds"] >= 2}
    verdict["search_works"] = all(verdict.values())
    out = {
        "freeze_sha256": RAW["freeze_sha256"], "replays": len(TRADES), "lot_size": LOT,
        "parity": {"trades": len([t for t in TRADES["PASSTHROUGH"] if t.get("net_pnl") is not None]),
                   "net": round(sum(t["net_pnl"] for t in TRADES["PASSTHROUGH"] if t.get("net_pnl") is not None), 2)},
        "walk_forward": {"REAL": real, "NULL": null, "references_on_oos_sessions": refs_oos,
                         "oos_sessions": OOS_DAYS, "verdict": verdict},
        "families": family_tables(), "alleles": allele_effects(), "generalisation": top_k_generalisation(),
        "persistence": persistence(),
        "final": final_profile(),
        "references_full": {name: row(trades, lab.FULL) for name, trades in REFS.items()},
        "history": RAW["history"],
    }
    lab.write_new(HERE / "results.json", out)
    print(json.dumps({"verdict": verdict, "real_oos": {k: real["oos"][k] for k in ("net", "trades", "dd")},
                      "null_oos": {k: null["oos"][k] for k in ("net", "trades", "dd")},
                      "refs_oos": {k: v["net"] for k, v in refs_oos.items()}}, indent=1))


if __name__ == "__main__":
    main()
