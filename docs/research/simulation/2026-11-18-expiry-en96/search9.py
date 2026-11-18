"""Stage B chronological selection and EN105's component combinations (IMPL9.md section 5).

Calendar: the frozen book's NIFTY sessions in date order. The first 100 form the initial history; outer blocks of 20
(the last one partial) are scored by a policy chosen only from the 60 sessions before the block (three inner blocks of
20). Independent-session results are path-free, so they are sliced from the full-calendar run; every inner and stitched
wallet is re-run from its own start. Nothing here reads a session at or after the outer block being chosen for.
"""
from dataclasses import replace
import math
import numpy as np
import round8  # noqa: F401
import lab9, families9 as F
from families9 import Spec

INITIAL, OUTER, INNER, NBLK = 100, 20, 60, 3
GENES = ("signal", "context", "entry", "contract", "management", "size")
GENE_FAMILIES = {"signal": ("EN96", "EN97"), "context": ("EN98",), "entry": ("EN99",), "contract": ("EN100",),
                 "management": ("EN101", "EN102"), "size": ("EN103",)}


def boundaries(n):
    return list(range(INITIAL, n, OUTER))


def blocks_of(s):
    idx = list(range(s - INNER, s)); k = INNER // NBLK
    return [idx[b * k:(b + 1) * k] for b in range(NBLK)]


def without_top2(vals):
    top = sorted(vals, reverse=True) + [0., 0.]
    return float(sum(vals) - max(top[0], 0.) - max(top[1], 0.))


def evaluate(book, bank, cid, rule, ref, s, genes=0):
    """One candidate's inner-window record at boundary s (all constraints of IMPL9 5.3)."""
    blocks = blocks_of(s); idx = [k for b in blocks for k in b]
    o = [bank[cid]["ordinary"][k] for k in idx]; a = [bank[cid]["adverse"][k] for k in idx]
    ra = [bank[ref]["adverse"][k] for k in idx]
    parents = sum(d["trades"] for d in o)
    active = sum(any(bank[cid]["ordinary"][k]["trades"] > 0 for k in b) for b in blocks)
    impr = [float(np.mean([bank[cid]["adverse"][k]["net"] - bank[ref]["adverse"][k]["net"] for k in b])) for b in blocks]
    med = float(np.median(impr))
    wo = lab9.wallet9([book[k] for k in idx], rule, "ordinary"); wa = lab9.wallet9([book[k] for k in idx], rule, "adverse")
    checks = dict(support=parents >= 10 and active >= 2, reconciled=bool(bank[cid].get("reconciled", True)),
                  no_halt=wo["halted"] == 0 and wa["halted"] == 0, wallet_positive=wo["P"] > 0 and wa["P"] > 0,
                  without_best_two=without_top2([d["net"] for d in o]) >= 0, median_block_improvement=med >= 0)
    return dict(id=cid, objective=round(med, 4), block_improvement=[round(x, 2) for x in impr], parents=parents, active_blocks=active,
                wallet_ordinary=round(wo["P"], 2), wallet_adverse=round(wa["P"], 2), liq_dd=wo["liq_dd"], halted=wo["halted"] + wa["halted"],
                inner_ordinary=round(sum(d["net"] for d in o), 2), inner_adverse=round(sum(d["net"] for d in a), 2),
                reference_inner_adverse=round(sum(d["net"] for d in ra), 2), checks=checks, passed=all(checks.values()), genes=genes)


def choose(records):
    ok = [r for r in records if r["passed"]]
    if not ok:
        fails = {}
        for r in records:
            for k, v in r["checks"].items():
                fails[k] = fails.get(k, 0) + (not v)
        return None, dict(reason="NO_CANDIDATE_PASSED", failed_check_counts=fails, candidates=len(records))
    best = min(ok, key=lambda r: (-r["objective"], r["liq_dd"], r["genes"], r["id"]))
    return best["id"], dict(reason="SELECTED", candidates=len(records), passed=len(ok))


def select_family(book, bank, rules, cands, ref, s, genes=None):
    recs = [evaluate(book, bank, c, rules[c], ref, s, (genes or {}).get(c, 0)) for c in cands]
    pick, why = choose(recs)
    return pick, why, recs


# ------------------------------------------------------------------ EN105 composition
def compose(sel_specs, g, one_lot=False):
    s = Spec()
    for k, name in enumerate(GENES):
        if not g[k] or sel_specs.get(name) is None:
            continue
        c = sel_specs[name]
        if name == "signal":
            s = replace(s, rep=c.rep, H=c.H, p=c.p)
        elif name == "context":
            s = replace(s, context=c.context)
        elif name == "entry":
            s = replace(s, entry=c.entry)
        elif name == "contract":
            s = replace(s, chooser=c.chooser)
        elif name == "management":
            s = replace(s, mgmt=c.mgmt)
        elif name == "size":
            s = replace(s, size=c.size)
    return replace(s, one_lot=True) if one_lot else s


def genotypes():
    return [tuple((n >> (5 - k)) & 1 for k in range(6)) for n in range(64)]


def gid(g):
    return "".join(map(str, g))
