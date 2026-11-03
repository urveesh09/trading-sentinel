"""Every E03.2 diagnostic in one reproducible run -> diagnostics.json. In-sample except where stated.

  morning_by_hour     the frozen morning test's E03 tickets by entry hour (from morning-results.json)
  tickets             E03.1's own tickets by hour, price, lots and exit, each year
  direction           E03.1 with its signal, the signal reversed, and the signal's minute with a random side (40 seeds)
  buy_limit           the most E03 / E03.1 may pay above the decision ask (E03.1: 10%), three fill levels, each year
  capacity            the whole book scaled k times (cash, reserves, brakes, lots), per-Rs-25,000 results
  two_tickets         days with two tickets, and whether an open runner ever blocked a later signal
  genome_family       share of all leave-one-year-out genomes positive / positive without the best day on the unseen year
"""
from __future__ import annotations
import collections, csv, json, random
from dataclasses import replace
from pathlib import Path
import numpy as np
import e032_lab as Z

HERE = Path(__file__).resolve().parent
L, E = Z.L, Z.E


def summary(s):
    return {k: s[k] for k in ("net", "without_best", "worst", "drawdown", "trades")}


def morning_by_hour():
    r = json.loads((HERE / "morning-results.json").read_text(encoding="utf-8"))
    out = {}
    for arm in ("M_E03|ordinary", "M_E03|adverse"):
        by = collections.defaultdict(list)
        for x in r["tickets"][arm]:
            by[(x["entry_minute"] - 1) // 60].append(x)
        out[arm] = {f"{h:02d}:00": dict(tickets=len(v), net=round(sum(x["net"] for x in v), 2), wins=sum(x["net"] > 0 for x in v),
                                       exits=dict(collections.Counter(x["exits"][0][0] for x in v))) for h, v in sorted(by.items())}
    return out


def tickets(T):
    out = {}
    for y in (2024, 2025):
        r = Z.run(T[y], Z.E031, "ordinary", details=True)
        ps = [p for d in r["days"] for p in d["positions"]]
        keys = {"hour": lambda p: f"{(p['entry_i'] + 556) // 60}:00",
                "price": lambda p: "<8" if p["entry"] < 8 else "8-12" if p["entry"] < 12 else "12-16" if p["entry"] < 16 else "16+",
                "lots": lambda p: str(p["lots"]), "exit": lambda p: p["events"][-1]["reason"]}
        out[str(y)] = {}
        for name, fn in keys.items():
            g = collections.defaultdict(list)
            for p in ps:
                g[fn(p)].append(p["net"])
            out[str(y)][name] = {k: dict(tickets=len(v), net=round(sum(v), 2), wins=sum(x > 0 for x in v)) for k, v in sorted(g.items())}
    return out


def direction(T):
    real = L.directions; out = {}
    try:
        for name, fn in (("signal", real), ("reversed", lambda t, rule: -real(t, rule))):
            L.directions = fn
            out[name] = {f"{y}|{sc}": summary(Z.run(T[y], Z.E031, sc)["summary"]) for y in (2024, 2025) for sc in ("ordinary", "adverse")}
        for y in (2024, 2025):
            nets = []
            for seed in range(40):
                def fn(t, rule, seed=seed):
                    d = real(t, rule).copy(); rng = random.Random(f"{seed}-{t.day}")
                    for i in np.flatnonzero(d):
                        d[i] = rng.choice((1, -1))
                    return d
                L.directions = fn
                nets.append(Z.run(T[y], Z.E031)["summary"]["net"])
            out[f"signal_minute_random_side|{y}"] = dict(mean=round(float(np.mean(nets)), 2), median=round(float(np.median(nets)), 2),
                                                         p95=round(float(np.percentile(nets, 95)), 2))
    finally:
        L.directions = real
    return out


def buy_limit(T):
    both = T[2024] + T[2025]; out = {}
    for name, base in (("E03", Z.E03), ("E031", Z.E031)):
        for ch in (.10, .09, .08, .07, .065, .06, .055, .05, .045, .04):
            r = replace(base, chase=ch)
            out[f"{name}|{ch}"] = {f"{scope}|{sc}": Z.run(tape, r, sc)["summary"]["net"]
                                   for scope, tape in (("both", both), ("2024", T[2024]), ("2025", T[2025]))
                                   for sc in ("ordinary", "adverse", "catastrophe")}
    return out


def capacity(T, rule):
    both = T[2024] + T[2025]; out = {}
    for k in (1, 2, 4, 10, 20):
        r = replace(rule, max_lots=3 * k)
        for sc in ("ordinary", "adverse"):
            cash = peak = 25000. * k; days = []
            for t in both:
                dd = peak - cash
                scale = 0. if dd >= 4000 * k else .25 if dd >= 3000 * k else .5 if dd >= 1500 * k else 1.
                saved = E.BUDGET; E.BUDGET = 2500. * k
                try:
                    row = Z.run_day(t, r, sc, cash, min(E.BUDGET * scale, cash))
                finally:
                    E.BUDGET = saved
                cash = round(cash + row["net"], 2); peak = max(peak, cash); days.append(row)
            s = E.summary(days)
            out[f"{k}|{sc}"] = dict(cash=25000 * k, net=s["net"], per_25000=round(s["net"] / k, 2), worst=s["worst"],
                                    drawdown=s["drawdown"], trades=s["trades"])
    return out


def two_tickets(T):
    both = T[2024] + T[2025]
    r = Z.run(both, Z.E031, "ordinary", details=True)
    days = [d for d in r["days"] if d["trades"]]
    blocked = 0
    for d, t in zip(r["days"], both):
        dirs = L.directions(t, Z.E031)
        for p in d["positions"]:
            starts = [e["i"] for e in p["events"] if e.get("reason") == "TARGET_BASE"]
            if starts and d["trades"] < 2 and any(dirs[i] and t.minute[i] < 900 for i in range(starts[0], p["exit_i"])):
                blocked += 1
    return dict(days_with_tickets=len(days), two_ticket_days=sum(d["trades"] == 2 for d in days),
                pairs=[[round(d["positions"][0]["net"], 2), round(d["positions"][1]["net"], 2)] for d in days if d["trades"] == 2],
                runner_blocked_a_later_signal=blocked)


def genome_family():
    rows = list(csv.DictReader(open(HERE / "genome-trials.csv", encoding="utf-8")))
    out = {}
    for d, base in (("fit2024_test2025", 3528.74), ("fit2025_test2024", 8897.97)):
        sub = [x for x in rows if x["direction"] == d]
        out[d] = dict(evaluated=len(sub), positive=round(sum(float(x["test_o"]) > 0 for x in sub) / len(sub), 3),
                      positive_without_best=round(sum(float(x["test_exb_o"]) > 0 for x in sub) / len(sub), 3),
                      beat_e031=round(sum(float(x["test_o"]) > base for x in sub) / len(sub), 3))
    return out


def main():
    T = L.tapes()
    out = dict(morning_by_hour=morning_by_hour(), tickets=tickets(T), direction=direction(T), buy_limit=buy_limit(T),
               capacity=capacity(T, replace(Z.E031, chase=.08)), two_tickets=two_tickets(T), genome_family=genome_family())
    (HERE / "diagnostics.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(direction=out["direction"]["signal_minute_random_side|2024"], genome=out["genome_family"],
                          two=out["two_tickets"]["two_ticket_days"], cap=out["capacity"]["4|ordinary"]), indent=1))


if __name__ == "__main__":
    main()
