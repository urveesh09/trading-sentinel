"""After the score: a map of nearby exit rules on all 25 tickets (18 October breaks, 7 September).

September is seen now, so this picks nothing. E01.1 stays as frozen. It only asks whether a neighbour is so far ahead
that the next frozen test should carry it, and how sharply the result depends on each setting.
"""
from __future__ import annotations

import itertools
import json
from dataclasses import replace

import arms as M
import e011_lab as L
import panel as P
import score as Q
import sept as Z

STOPS = (.20, .25, .30)
BANKS = (("half", 2.0), ("recover", 2.0), ("none", None), ("recover", 1.0), ("half", 1.0), ("recover", 3.0))
FLOORS = ((1.0, .6), (1.5, .6), (2.0, .6), (3.0, .6), (4.0, .6), (2.0, .5), (2.0, .7), (1.0, .5), (1.0, .7))


def ticket(stop, bank, floor):
    mode, at = bank
    trails = ((floor[0], floor[1]), (4.0, .60)) if floor[0] < 4.0 else ((4.0, floor[1]),)
    return replace(L.E01, stop=stop, bank="half" if mode == "none" else mode, bank_at=at, trails=trails)


def main() -> None:
    rows = []
    sept = [(Z.Sept(d), Z.Sept(d, adverse=True)) for d in Z.DAYS]
    adm = [(o, a, P.admissions(o)) for o, a in sept]
    for stop, bank, floor in itertools.product(STOPS, BANKS, FLOORS):
        t = ticket(stop, bank, floor)
        oct_o = [r["net"] for r in Q.every_break(t, False)]
        oct_a = [r["net"] for r in Q.every_break(t, True)]
        sep_o, sep_a = [], []
        for o, a, items in adm:
            for i, symbol, _ in items:
                sep_o.append(L.net(P.run_ticket(o, i, symbol, t)))
                sep_a.append(L.net(P.run_ticket(a, i, symbol, t)))
        rows.append(dict(stop=stop, bank=bank[0], bank_at=bank[1], floor_from=floor[0], keep=floor[1],
                         oct=round(sum(oct_o), 0), oct_adv=round(sum(oct_a), 0), sep=round(sum(sep_o), 0), sep_adv=round(sum(sep_a), 0),
                         total=round(sum(oct_o) + sum(sep_o), 0), total_adv=round(sum(oct_a) + sum(sep_a), 0),
                         oct13=max(oct_o), worst=min(oct_o + sep_o)))
    rows.sort(key=lambda r: -min(r["total"], r["total_adv"]))
    (L.HERE / "round2-map.json").write_text(json.dumps(rows, indent=0) + "\n")
    print("combinations", len(rows))
    for r in rows[:14]:
        print(r)
    print("...")
    print("frozen E01.1", [r for r in rows if r["stop"] == .25 and r["bank"] == "recover" and r["bank_at"] == 2.0 and r["floor_from"] == 2.0 and r["keep"] == .6])
    print("frozen no-bank", [r for r in rows if r["stop"] == .25 and r["bank"] == "none" and r["floor_from"] == 2.0 and r["keep"] == .6])
    print("E01", [r for r in rows if r["stop"] == .30 and r["bank"] == "half" and r["bank_at"] == 2.0 and r["floor_from"] == 4.0 and r["keep"] == .6])
    for name, field in (("stop", "stop"), ("bank", "bank"), ("floor_from", "floor_from"), ("keep", "keep")):
        groups = {}
        for r in rows:
            groups.setdefault(r[field], []).append(r["total"])
        print(name, {k: round(sum(v) / len(v)) for k, v in sorted(groups.items(), key=lambda x: str(x[0]))})


if __name__ == "__main__":
    main()
