"""Post-score: (1) permutation test of E03.1's put-call ticket difference, hero day removed; (2) the exact E03.2
candidate (PUT2 + 8% buy limit + sell everything from 15:14) at three fill levels, each year and continuous. IN-SAMPLE.
-> final-checks.json
"""
from __future__ import annotations
import json, random, statistics as st
from dataclasses import replace
from pathlib import Path
import r8b_lab as R

HERE = Path(__file__).resolve().parent


def main():
    T = R.L.tapes(); both = T[2024] + T[2025]; out = {}
    r = R.run(both, R.E031, details=True)
    tickets = [(p["direction"], p["net"], p["day"]) for d in r["days"] for p in d["positions"]]
    hero = max(tickets, key=lambda x: x[1])
    rest = [x for x in tickets if x is not hero]
    pe = [n for s, n, _ in rest if s < 0]; ce = [n for s, n, _ in rest if s > 0]
    obs = st.mean(pe) - st.mean(ce); pool = pe + ce; rng = random.Random(20261103); hits = 0
    for _ in range(100000):
        rng.shuffle(pool)
        if st.mean(pool[:len(pe)]) - st.mean(pool[len(pe):]) >= obs:
            hits += 1
    out["permutation_ex_hero"] = dict(pe_tickets=len(pe), ce_tickets=len(ce), pe_mean=round(st.mean(pe), 2), ce_mean=round(st.mean(ce), 2),
                                      observed_difference=round(obs, 2), one_sided_p=round(hits / 100000, 4), hero=hero)
    cand = replace(R.E031, put_mult=2., chase=.08, flat=914)
    out["E032_candidate"] = {}
    for name, rule in (("E031", R.E031), ("PUT2", replace(R.E031, put_mult=2.)), ("E032", cand)):
        row = {}
        for scope, tapes in (("2024", T[2024]), ("2025", T[2025]), ("both", both)):
            for sc in ("ordinary", "adverse", "catastrophe"):
                s = R.run(tapes, rule, sc)["summary"]
                row[f"{scope}|{sc}"] = {k: s[k] for k in ("net", "without_best", "worst", "drawdown", "trades")}
        out["E032_candidate"][name] = row
        print(name, {k: (v["net"], v["worst"], v["drawdown"]) for k, v in row.items()}, flush=True)
    print(json.dumps(out["permutation_ex_hero"]))
    (HERE / "final-checks.json").write_text(json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
