"""Read the evolution round's results.json and print the report tables (no rescoring)."""
import json
import sys
from pathlib import Path

OUT = Path(r"C:\Users\Urveesh\Desktop\trading-sentinel\docs\research\fno\2026-10-27-evolution")
r = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
D, H, E = r["decision"], r["holdout"], r["evaluations"]


def short(k):
    return " ".join(f"{p.split('=')[0][:6]}={p.split('=')[1]}" for p in k.split("|"))


print("verdict", D["verdict"], "| recommended", D["recommended"], "| parity", D["shipped_genome_equals_current_on_A"],
      "| B dd limit", D["b_drawdown_limit"], "| shipped fitness", r["fitness_shipped"], "| evaluations", len(E))
print("\n== Generations")
for h in r["history"]:
    print(f"  gen {h['generation']:2} best {h['best_fitness']:7.3f} median {h['median_fitness']:7.3f} evaluated {h['evaluated_total']}")
print("\n== Holdout (finalists in plateau order, then shipped, O27 pick)")
for k in [*D["finalists"], r["shipped"], *r["o27_pick"]]:
    h = H[k]
    tag = "FINALIST" if k in D["finalists"] else ("SHIPPED" if k == r["shipped"] else "O27 PICK")
    chk = D["checks"].get(k)
    print(f"-- {tag} plateau={D['plateau_fitness'].get(k)} fit={E.get(k, {}).get('fitness')} "
          f"{'' if chk is None else ('PASS' if all(chk.values()) else 'fail ' + str(chk))}  a_match={h['a_matches_evolution']}")
    print("   ", short(k))
    for w in ("A", "B", "B_without_motivating_days", "FULL"):
        m = h[w]
        print(f"    {w:26} {m['trades']:3}t net {m['net_pnl']:8.0f} xbest {m['net_excluding_best_winner']:8.0f} "
              f"dd {m['max_drawdown']:7.0f} pf {m['profit_factor']} days {m['trade_days']}/{m['sessions']} "
              f"green {m['green_days']} red {m['red_days']} gw {m['green_weeks']}/{m['weeks']} unres {m['unresolved']} "
              f"lot {m['net_per_lot']:.0f}")
print("\n== Top 15 evaluated on A by fitness")
for k, s in sorted(E.items(), key=lambda kv: -kv[1]["fitness"])[:15]:
    m = s["metrics"]
    print(f"  {s['fitness']:7.3f} g{s['generation']:2} {m['trades']:3}t {m['net_pnl']:8.0f} dd {m['max_drawdown']:6.0f} "
          f"halves {m.get('halves')} | {short(k)}")
print("\n== Allele effects (all evaluated genomes on A): n, median fitness, best, feasible share")
for gene, alleles in r["allele_effects"].items():
    print(f"  {gene:18} " + "  ".join(f"{a}: n{v['n']} med {v['median_fitness']:.2f} best {v['best_fitness']:.2f} "
                                       f"feas {v['feasible_share']:.0%}" for a, v in alleles.items()))
for k in sys.argv[1:]:
    import hashlib
    d = hashlib.sha256(k.encode()).hexdigest()[:16]
    rep = json.loads((OUT / "_local" / "FULL" / f"{d}.json").read_text(encoding="utf-8"))
    print(f"\n== Trades (FULL) of {short(k)}")
    for t in rep["trades"]:
        print("  ", t["entry_time"][:16], t.get("direction"), t.get("tradingsymbol"), t.get("lots_at_exit"),
              (t.get("exit_time") or "")[11:16], t.get("exit_reason"), round(t.get("net_pnl", 0)))
