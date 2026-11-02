"""Selection luck, before the exam: had the search seen only two years, what would it have picked, and how did that do on the third?

Every book from screens 1-3 competes. Pick: highest two-year net whose worst annual closed fall stayed at or under N07's over those years.
Also: how often does a book beat N07 in the unseen year after beating it in both seen ones? Reads saved replays only. Writes heldout.json.
"""
import json
from pathlib import Path

from analyze_screen import A, YEARS, closed_dd, stored

HERE = Path(__file__).resolve().parent
refs = {y: {**json.loads((A / "_local" / f"keys-reference-{y}.json").read_text()), **json.loads((A / "_local" / f"keys-candidate-{y}.json").read_text())} for y in YEARS}
books = {"N07": {y: refs[y]["NORMAL|PREMIUM_STALL"] for y in YEARS}}
for screen in ("keys-screen", "keys-screen2", "keys-screen3"):
    keys = {y: json.loads((HERE / "_local" / f"{screen}-{y}.json").read_text()) for y in YEARS}
    for name in keys["2024"]:
        books[name] = {y: keys[y][name] for y in YEARS}
net, dd = {}, {}
for name, by_year in books.items():
    net[name], dd[name] = {}, {}
    for y in YEARS:
        trades = stored(by_year[y])
        net[name][y] = sum(t["net_pnl"] for t in trades)
        dd[name][y] = closed_dd(trades)
out = {"books": len(books), "held_out": {}}
for held in YEARS:
    seen = [y for y in YEARS if y != held]
    limit = max(dd["N07"][y] for y in seen)
    allowed = [n for n in books if max(dd[n][y] for y in seen) <= limit + 1e-9]
    pick = max(allowed, key=lambda n: sum(net[n][y] for y in seen))
    beat_both = [n for n in books if n != "N07" and all(net[n][y] > net["N07"][y] for y in seen)]
    held_up = [n for n in beat_both if net[n][held] > net["N07"][held]]
    out["held_out"][held] = {"pick": pick, "pick_net": round(net[pick][held]), "n07_net": round(net["N07"][held]), "books_beating_n07_in_both_seen_years": len(beat_both), "of_which_beat_n07_in_the_held_year": len(held_up)}
    print(held, out["held_out"][held])
n08 = "COMBO|WELC"
print("N08 by year:", {y: round(net[n08][y]) for y in YEARS}, "N07:", {y: round(net["N07"][y]) for y in YEARS})
(HERE / "heldout.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
