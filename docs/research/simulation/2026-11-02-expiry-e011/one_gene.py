"""One change at a time from E01, session by session, ordinary and adverse quotes.

A rule worth keeping should help several days and hurt few, not earn its gain on Oct 13 alone. The lottery ticket's
genes, then A's and B's. Seen sessions only.
"""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import time
from pathlib import Path

import e011_lab as L
import genome as G
import expiry_paper as EP

KEYS = L.recorded_keys()
SO = [L.Recorded(d, u) for d, u in KEYS]
SA = [L.Recorded(d, u, True) for d, u in KEYS]


def row(name, base, fn):
    a = [fn(S) for S in SO]
    b = [fn(S) for S in SA]
    d = [round(x - y, 2) for x, y in zip(a, base[0])]
    up = sum(x > .01 for x in d)
    dn = sum(x < -.01 for x in d)
    ex = sum(a) - max(a)
    print(f"{name:42s} net {sum(a):9.0f} ({sum(a)-sum(base[0]):+7.0f}) adv {sum(b):9.0f} exbest {ex:7.0f} worst {min(a):7.0f} up/dn {up}/{dn} | " + " ".join(f"{x:+6.0f}" for x in d), flush=True)
    return dict(name=name, net=sum(a), adverse=sum(b), exbest=ex, worst=min(a), per=a, delta=d)


def ticket_table():
    out = []
    e01 = G.e01_genome()
    fn = lambda g: (lambda S: L.net(L.run_c(S, G.to_ticket(g), "X")))
    base = ([fn(e01)(S) for S in SO], [fn(e01)(S) for S in SA])
    print("E01 ticket per session", base[0], "net", round(sum(base[0]), 2), "adverse", round(sum(base[1]), 2))
    for gene, values in G.SPACE.items():
        for v in values:
            if v == e01[gene]:
                continue
            out.append(row(f"{gene}={v}", base, fn({**e01, gene: v})))
    return out


def a_table():
    A = EP.POLICIES["A"]
    fn = lambda p=A, back=EP.FAIL_BACK_WIDTH, n=EP.A_MAX_TRADES: (lambda S: L.net(L.run_a(S, p, back, n)))
    base = ([fn()(S) for S in SO], [fn()(S) for S in SA])
    print("\nA per session", base[0], "net", round(sum(base[0]), 2), "adverse", round(sum(base[1]), 2))
    out = []
    for name, kw in {
        "stop .20": dict(p=replace(A, hard_stop=.20)), "stop .25": dict(p=replace(A, hard_stop=.25)), "stop .40": dict(p=replace(A, hard_stop=.40)),
        "time stop off": dict(p=replace(A, time_stop=None)), "time stop 240s/.10": dict(p=replace(A, time_stop=(240, .10))),
        "time stop 900s/.15": dict(p=replace(A, time_stop=(900, .15))), "time stop 480s/.05": dict(p=replace(A, time_stop=(480, .05))),
        "time stop 480s/.25": dict(p=replace(A, time_stop=(480, .25))),
        "back 0": dict(back=0.0), "back .5": dict(back=.5), "back off": dict(back=None),
        "trades 1": dict(n=1), "trades 3": dict(n=3),
        "bank +60%": dict(p=replace(A, bank_at=.60)), "bank +100%": dict(p=replace(A, bank_at=1.0)),
        "bank stop 1.0": dict(p=replace(A, bank_stop=1.0)), "bank stop 1.2": dict(p=replace(A, bank_stop=1.2)),
        "trail 1x keeps 60": dict(p=replace(A, trails=((1.0, .60), (2.0, .80)))), "trail 2x keeps 70": dict(p=replace(A, trails=((1.0, .70), (2.0, .70)))),
        "late off": dict(p=replace(A, late=None)), "late keeps 75": dict(p=replace(A, late=(time(15, 0), .75))),
        "flat 15:28": dict(p=replace(A, flat_at=time(15, 28))),
    }.items():
        out.append(row("A " + name, base, fn(**kw)))
    return out


def b_table():
    fn = lambda **kw: (lambda S: L.net(L.run_b(S, **kw)))
    base = ([fn()(S) for S in SO], [fn()(S) for S in SA])
    print("\nB per session", base[0], "net", round(sum(base[0]), 2), "adverse", round(sum(base[1]), 2))
    out = []
    for t in (.10, .15, .25, .30, .40, .50):
        out.append(row(f"B target {t}", base, fn(target=t)))
    for f in (time(15, 20), time(15, 24), time(15, 26), time(15, 27), time(15, 28), time(15, 29), time(15, 30), time(15, 33)):
        out.append(row(f"B flat {f}", base, fn(flat_at=f)))
    return out


if __name__ == "__main__":
    print("days", [d[5:] for d, _ in KEYS])
    result = dict(ticket=ticket_table(), a=a_table(), b=b_table())
    (Path(__file__).parent / "_local/one_gene.json").write_text(json.dumps(result, indent=1, default=str) + "\n")
