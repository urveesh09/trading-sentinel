"""Every E03.2 trial, appended to trials.csv (never rewritten). In-sample: the afternoons are seen.

    python trials.py <group>      groups are defined in GROUPS below, fixed before the group is run

Each trial: independent 2024 and 2025 books (ordinary, adverse) and the continuous 2024-2025 book
(ordinary, adverse, severe). The pick score is the worst of the four independent-year results
without their best day, so one hero day or one good year cannot carry a rule.
"""
from __future__ import annotations
import csv, itertools, json, sys, time
from dataclasses import asdict, replace
from pathlib import Path
import e032_lab as Z

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "trials.csv"
FIELDS = ["group", "name", "key", "params", "score",
          "net_2024_o", "net_2024_a", "net_2025_o", "net_2025_a", "exb_2024_o", "exb_2024_a", "exb_2025_o", "exb_2025_a",
          "worst_o", "worst_a", "both_o", "both_a", "both_severe", "dd_both_o", "dd_both_a", "roll_both_o", "rolls_both_o",
          "trades_both_o", "inc_vs_e031_o", "inc_vs_e031_a", "at"]


def grid(**axes):
    names = list(axes)
    return [dict(zip(names, v)) for v in itertools.product(*axes.values())]


GROUPS = {
    "baseline": [("E03", {}, Z.E03), ("E031", {}, Z.E031)],
    "roll": grid(roll_share=(.25, .5, 1.), roll_on=("both", "target", "base"), roll_stop=(.5, 1.), roll_hold=(10, 30),
                 roll_target=(9., 0.), roll_min=(1., 2.)),
    "earn": grid(earn_share=(.1, .2, .3), earn_cap=(1.5, 2.)),
    # Same signal, near-the-money instrument, one lot, Rs 6,500 full-premium reserve per ticket.
    "atm": [dict(instrument="atm", ticket_room=6500., premium_low=15., premium_high=95., max_lots=1, split=False, lock_arm=0.,
                 stop=st, target=tg, hold=h, arm=a, keep=.6) for st in (.15, .25) for tg in (.3, .6, 1.) for h in (8, 15) for a in (.2, .4)],
    # The runner needs two lots: prefer the nearest strike where two (or three) lots fit the same Rs 1,250.
    "prefer": grid(prefer_lots=(2, 3), prefer_only=(False, True), premium_low=(3., 5.)),
}


def evaluate(rule, T):
    both = T[2024] + T[2025]; row = {}
    for y in (2024, 2025):
        for sc, tag in (("ordinary", "o"), ("adverse", "a")):
            s = Z.run(T[y], rule, sc)["summary"]
            row[f"net_{y}_{tag}"] = s["net"]; row[f"exb_{y}_{tag}"] = s["without_best"]
            row[f"worst_{tag}"] = min(row.get(f"worst_{tag}", 0.), s["worst"])
    for sc, tag in (("ordinary", "o"), ("adverse", "a"), ("catastrophe", "severe")):
        s = Z.run(both, rule, sc)["summary"]
        row[f"both_{tag}"] = s["net"]
        if tag != "severe":
            row[f"dd_both_{tag}"] = s["drawdown"]
        if tag == "o":
            row["roll_both_o"] = s["roll"]; row["rolls_both_o"] = s["rolls"]; row["trades_both_o"] = s["trades"]
    row["score"] = min(row[f"exb_{y}_{t}"] for y in (2024, 2025) for t in "oa")
    return row


def main(group):
    T = Z.L.tapes()
    base = evaluate(Z.E031, T)
    trials = GROUPS[group]
    new = not LEDGER.exists()
    with open(LEDGER, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        if new:
            w.writeheader()
        for n, item in enumerate(trials):
            if isinstance(item, tuple):
                name, params, rule = item
            else:
                params = item; name = f"{group}-{n:03d}"; rule = replace(Z.E031, **params)
            row = evaluate(rule, T)
            row.update(group=group, name=name, key=rule.key, params=json.dumps(params, sort_keys=True),
                       inc_vs_e031_o=round(row["both_o"] - base["both_o"], 2), inc_vs_e031_a=round(row["both_a"] - base["both_a"], 2),
                       at=time.strftime("%Y-%m-%dT%H:%M:%S"))
            w.writerow({k: row.get(k) for k in FIELDS}); f.flush()
            print(name, params, {k: row[k] for k in ("score", "both_o", "both_a", "both_severe", "worst_o", "roll_both_o", "rolls_both_o")}, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
