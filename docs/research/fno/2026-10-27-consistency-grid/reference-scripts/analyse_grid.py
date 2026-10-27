"""Read results.json of the frozen grid and print the report tables (no rescoring)."""
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

OUT = Path(r"C:\Users\Urveesh\Desktop\trading-sentinel\docs\research\fno\2026-10-27-consistency-grid")
r = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
M, D = r["metrics"], r["decision"]
CUR = "OR30|LOCK_LIVE|T45|TR1.0"
ranked = [a for a in M if not a.startswith("PARITY")]


def row(arm):
    a, b, f = M[arm]["A_select"], M[arm]["B_check"], M[arm]["FULL"]
    chk = D["checks"].get(arm)
    return (f"{arm:30} pl={D['plateau_cs'][arm]:5.2f} | A {a['trades']:2}t {a['net_pnl']:7.0f} xb {a['net_excluding_best_winner']:7.0f} "
            f"dd {a['max_drawdown']:6.0f} cs {a['cs']:5.2f} gw {a['green_weeks']}/{a['weeks']} | B {b['trades']:2}t "
            f"{b['net_pnl']:7.0f} dd {b['max_drawdown']:6.0f} | F {f['trades']:2}t {f['net_pnl']:7.0f} "
            f"xb {f['net_excluding_best_winner']:7.0f} dd {f['max_drawdown']:6.0f} gd {f['green_days']}/{f['red_days']}r "
            f"gw {f['green_weeks']}/{f['weeks']} pf {f['profit_factor']} lot {f['net_per_lot']:7.0f} "
            f"{'' if chk is None else ('PASS' if all(chk.values()) else 'fail')}")


print("verdict", D["verdict"], "recommended", D["recommended"], "current_rank", D["current_rank"],
      "eligible", D["eligible_count"], "B dd limit", D["b_drawdown_limit"],
      "parity", D["parity_generic_path_equals_current"])
print("\n== CURRENT"); print(row(CUR))
print("\n== Top 25 by the frozen rank")
for i, a in enumerate(D["rank"][:25], 1):
    print(f"{i:3}", row(a))
print("\n== Best eligible per entry")
entries = sorted({a.split("|")[0] for a in ranked})
for e in entries:
    el = [a for a in D["rank"] if a.startswith(e + "|")]
    if el:
        print(f"{e:14} rank {D['rank'].index(el[0]) + 1:3}", row(el[0]))
    else:
        best = max((a for a in ranked if a.startswith(e + "|")), key=lambda a: M[a]["A_select"]["cs"])
        print(f"{e:14} none eligible; best A cs:", row(best))
print("\n== Most earning (full window) for contrast")
for a in sorted(ranked, key=lambda a: -M[a]["FULL"]["net_pnl"])[:5]:
    print(row(a))
print("\n== Axis effects (median over arms): A cs, full net, full dd, full trades, share of arms with full net>0")
for axis, pos in (("entry", 0), ("lock", 1), ("time", 2), ("trail", 3)):
    groups = defaultdict(list)
    for a in ranked:
        groups[a.split("|")[pos]].append(a)
    for k, arms in sorted(groups.items()):
        print(f"  {axis:5} {k:14} n={len(arms):3} A_cs {statistics.median(M[a]['A_select']['cs'] for a in arms):6.2f} "
              f"full_net {statistics.median(M[a]['FULL']['net_pnl'] for a in arms):8.0f} "
              f"full_dd {statistics.median(M[a]['FULL']['max_drawdown'] for a in arms):7.0f} "
              f"trades {statistics.median(M[a]['FULL']['trades'] for a in arms):4.0f} "
              f"pos {sum(M[a]['FULL']['net_pnl'] > 0 for a in arms) / len(arms):4.0%}")
print("\n== EMA on vs off, same family and exit (full window net / A cs)")
for fam in ("OR30", "OR20", "OR45", "CONFIRM1", "CONT"):
    better = sum(M[a.replace(fam + "|", fam + "_NOEMA|", 1)]["FULL"]["net_pnl"] > M[a]["FULL"]["net_pnl"]
                 for a in ranked if a.split("|")[0] == fam)
    print(f"  {fam:9} no-EMA beats EMA on full net in {better}/36 exits")
print("\n== How many arms are positive in BOTH A and B:",
      sum(M[a]["A_select"]["net_pnl"] > 0 and M[a]["B_check"]["net_pnl"] > 0 for a in ranked), "of", len(ranked))
print("   positive full window:", sum(M[a]["FULL"]["net_pnl"] > 0 for a in ranked),
      " full net ex best > 0:", sum(M[a]["FULL"]["net_excluding_best_winner"] > 0 for a in ranked))
print("   CURRENT full window percentile of CS:",
      round(100 * sum(M[a]["FULL"]["cs"] < M[CUR]["FULL"]["cs"] for a in ranked) / len(ranked)))
for arm in sys.argv[1:]:
    rep = json.loads((OUT / "_local" / "arms" / (arm.replace("|", "__") + ".json")).read_text(encoding="utf-8"))
    print(f"\n== Trades of {arm}")
    for t in rep["trades"]:
        print("  ", t["entry_time"][:16], t.get("direction"), t.get("tradingsymbol"), t.get("lots_at_exit"),
              t.get("exit_time", "")[11:16], t.get("exit_reason"), round(t.get("net_pnl", 0)))
    print("   funnel:", {k: v for k, v in rep["funnel"].items() if v and not k.startswith("engine:")})
