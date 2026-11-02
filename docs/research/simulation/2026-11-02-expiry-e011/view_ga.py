"""Print the genome's survivors and the leave-one-out folds."""
import json
from pathlib import Path

GA = Path(__file__).parent / "_local/ga"
for p in sorted(GA.glob("full-seed*.json")):
    rows = json.loads(p.read_text())
    print(p.name)
    for r in rows[:3]:
        per = [r["per"][d][0] for d in sorted(r["per"])]
        print(" score", round(r["score"]), "net", round(sum(per)), "exbest", round(sum(per) - max(per)), "worst", min(per), "tickets", sum(r["per"][d][1] for d in r["per"]))
        print("   per", per)
        print("   diff", r["diff"])
folds = sorted(GA.glob("fold-*.json"))
if folds:
    total = 0
    for p in folds:
        r = json.loads(p.read_text())
        total += r["held_net"]
        print(r["held"], "held net", r["held_net"], "tickets", r["held_tickets"], "train", round(r["train"]), "diff", r["diff"])
    print("folds total", round(total, 2))
