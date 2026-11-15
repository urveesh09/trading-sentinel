"""SN222-SN227 shared: every structure x k x exit x hedge of the PLAN on one sample, cached per (sample, structure) in
_local/grid-<sample>-<structure>.pkl (each slice well under 9 minutes); trend filters are applied afterwards from the
entry-day pass table, because a filter only skips weeks.

    python grid.py SAMPLE [STRUCTURE ...]      # builds the missing slices (seen samples only; EXAM needs SN228)

A row is (entry, expiry, exit_day, net, reason, orders, hedge_costs, wing_clamped)."""
from __future__ import annotations

import pickle
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wk3  # noqa: E402

wk = wk3.wk


def _slice_path(sample, struct):
    return wk3.LOCAL / f"grid-{sample}-{struct.replace(' ', '_').replace('/', '-')}.pkl"


def build(sample, struct):
    p = _slice_path(sample, struct)
    if p.exists():
        return
    s = wk3.sample(sample)
    out = {}
    for k in wk3.KS:
        for ex in wk3.EXITS:
            if k == 1 and ex not in ("settle", "settle stop1"):
                continue
            for h in wk3.HEDGES:
                rows = []
                for t in wk3.book3(s, struct, k, ex, h):
                    rows.append((t["entry"], t["expiry"], t["exit_day"], t["net"], t["reason"], t["orders"], t["hedge_costs"],
                                 t["wing_clamped"]))
                out[(struct, k, ex, h)] = rows
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL))
    tmp.replace(p)


def filter_table(sample):
    """{filter: set(entry days that pass)} over every entry day any base trade used."""
    p = wk3.LOCAL / f"grid-{sample}-filters.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    s = wk3.sample(sample)
    days = set()
    for e, ds in s.weeks:
        for st in wk3.STRUCTURES:
            for k in wk3.KS:
                t = wk3.base_trade(s, e, ds, st, k)
                if t is not None:
                    days.add(t["entry"])
    tab = {f: {d for d in days if wk3.passes(s, d, flt)} for f, flt in wk3.FILTERS.items()}
    p.write_bytes(pickle.dumps(tab))
    return tab


_G = {}


def load(sample):
    if sample not in _G:
        g = {}
        for st in wk3.STRUCTURES:
            p = _slice_path(sample, st)
            if not p.exists():
                raise SystemExit(f"grid slice missing: {p.name} (run: python grid.py {sample})")
            g.update(pickle.loads(p.read_bytes()))
        _G[sample] = (g, filter_table(sample))
    return _G[sample]


def rows(sample, v):
    """Rows of variant v = (structure, k, exit, hedge, filter)."""
    g, ft = load(sample)
    st, k, ex, h, f = v
    base = g[(st, k, ex, h)]
    if f == "none":
        return base
    ok = ft[f]
    return [r for r in base if r[0] in ok]


def summary(rs, W, lots=1):
    rr = [{"entry": r[0], "expiry": r[1], "exit_day": r[2], "net": r[3], "wing_clamped": r[7], "orders": r[5],
           "hedge_costs": r[6]} for r in rs]
    return wk3.summary(rr, W, lots)


def lots_of(v):
    h = wk3.HEDGES[v[3]]
    return h["lots"] if h else 1


def W_of(sample):
    return wk3.sample(sample).W if sample != "EXAM" else None


if __name__ == "__main__":
    smp = sys.argv[1]
    if smp not in wk3.SEEN:
        raise SystemExit("grid.py builds the seen samples only")
    todo = sys.argv[2:] or list(wk3.STRUCTURES)
    for st in todo:
        t0 = time.time()
        build(smp, st)
        print(f"grid {smp} {st} done {time.time() - t0:.0f}s", flush=True)
    filter_table(smp)
    print(f"grid {smp} filters done", flush=True)


_T = {}


def table():
    """{variant: {sample: summary (per option lot)}} for every PLAN variant on the four seen samples (cached)."""
    if "t" not in _T:
        p = wk3.LOCAL / "grid-table.pkl"
        if p.exists():
            _T["t"] = pickle.loads(p.read_bytes())
        else:
            t = {}
            for v in wk3.variants():
                t[v] = {n: summary(rows(n, v), wk3.sample(n).W, lots_of(v)) for n in wk3.SEEN}
            p.write_bytes(pickle.dumps(t))
            _T["t"] = t
    return _T["t"]


def line(v, row):
    return (f"{wk3.vname(v):46s} " + " | ".join(f"{n} {row[n]['net']:>9} ({row[n]['trades']}w mo {row[n]['worst_month']:>7})" for n in wk3.SEEN)
            + f" | min/wk {min(row[n]['per_week'] for n in wk3.SEEN):>7.0f}")
