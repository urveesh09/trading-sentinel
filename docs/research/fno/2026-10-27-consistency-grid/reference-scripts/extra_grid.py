import json, statistics
from pathlib import Path
OUT = Path(r"C:\Users\Urveesh\Desktop\trading-sentinel\docs\research\fno\2026-10-27-consistency-grid")
r = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
M, D = r["metrics"], r["decision"]
ranked = [a for a in M if not a.startswith("PARITY")]
print("EMA off vs on, by window: arms (of 36) where no-EMA net is higher; median net EMA / no-EMA")
for fam in ("OR30", "OR20", "OR45", "CONFIRM1", "CONT"):
    for w in ("A_select", "B_check"):
        on = [a for a in ranked if a.split("|")[0] == fam]
        off = [a.replace(fam + "|", fam + "_NOEMA|", 1) for a in on]
        better = sum(M[b][w]["net_pnl"] > M[a][w]["net_pnl"] for a, b in zip(on, off))
        print(f"  {fam:9} {w:8} {better:2}/36  median {statistics.median(M[a][w]['net_pnl'] for a in on):8.0f} -> "
              f"{statistics.median(M[b][w]['net_pnl'] for b in off):8.0f}")
unres = {a: (M[a]["A_select"]["unresolved"], M[a]["B_check"]["unresolved"]) for a in ranked}
print("arms with unresolved trades:", sum(1 for v in unres.values() if sum(v)), "| in B:", sum(1 for v in unres.values() if v[1]))
print("unresolved in top 25:", {a: unres[a] for a in D["rank"][:25] if sum(unres[a])})
print("notes CURRENT:", M["OR30|LOCK_LIVE|T45|TR1.0"]["notes"])
print("notes pick:", M[D["recommended"]]["notes"])
for a in (D["recommended"], "OR20_NOEMA|LOCK_LATE|T75|TR1.5", "OR30|LOCK_LIVE|T45|TR1.0"):
    rep = json.loads((OUT / "_local" / "arms" / (a.replace("|", "__") + ".json")).read_text(encoding="utf-8"))
    nets = sorted((t["net_pnl"] for t in rep["trades"] if "net_pnl" in t), reverse=True)
    days = {}
    for t in rep["trades"]:
        if "net_pnl" in t:
            days[t["entry_time"][:10]] = days.get(t["entry_time"][:10], 0) + t["net_pnl"]
    print(f"{a}: total {sum(nets):.0f}, top-2 {sum(nets[:2]):.0f}, rest {sum(nets[2:]):.0f}; median trade {statistics.median(nets):.0f}; "
          f"trade days {len(days)} of 29; green {sum(v > 0 for v in days.values())}; worst day {min(days.values()):.0f}")
# family counts in rank
from collections import Counter
print("eligible by entry:", Counter(a.split('|')[0] for a in D["rank"]))
print("B trades of eligible arms == 0:", sum(M[a]["B_check"]["trades"] == 0 for a in D["rank"]), "of", len(D["rank"]))
first_traded = next((i + 1, a) for i, a in enumerate(D["rank"]) if M[a]["B_check"]["trades"] > 0 and all(D["checks"][a].values()))
print("first ranked passing arm WITH B trades (post hoc, not the frozen rule):", first_traded)
