"""The E03-family exam on NIFTY 2023 (EXAM_E03_FAMILY.md + EXAM_E032_ADDENDUM.md + EXAM_EN_ADDENDUM.md), scored ONCE.

Refuses unless OWNER_WORD.md (the owner's assignment of NIFTY 2023 to this exam) and freeze-exam.json are
committed and every frozen file is unchanged. 2023 rows come from the sealed selected export
2026-11-02-expiry-e02/_local/data.sqlite (hash-checked against its data-binding.json), built into tapes exactly
as data.load_year builds 2024/2025. Writes exam2023-results.json once (refuses to overwrite)."""
from __future__ import annotations
import hashlib, json, math, random, statistics as st, subprocess, sys
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import numpy as np
import en_lab as N

HERE = Path(__file__).resolve().parent
R, L, X, E = N.R, N.L, N.X, N.E
D = X.D
sys.path.insert(0, str(HERE.parent / "2026-11-03-expiry-auction"))
import riskdial as RD  # noqa: E402
SEALED = HERE.parent / "2026-11-02-expiry-e02/_local/data.sqlite"
BINDING = HERE.parent / "2026-11-02-expiry-e02/data-binding.json"
FILES = ("EXAM_EN_ADDENDUM.md", "exam2023.py", "en_lab.py", "en_base.py", "OWNER_WORD.md")
SC = ("ordinary", "adverse", "catastrophe")
SEEDS = 40


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while b := f.read(1 << 20): h.update(b)
    return h.hexdigest()


def git(*a):return subprocess.run(("git",) + a, cwd=HERE, capture_output=True, text=True).stdout.strip()


def freeze():
    assert not (HERE / "exam2023-results.json").exists()
    files = {f: sha(HERE / f) for f in FILES if (HERE / f).exists()}
    (HERE / "freeze-exam.json").write_text(json.dumps(dict(files=files, head=git("rev-parse", "HEAD")), indent=2) + "\n")
    print("FROZEN", files)


def gate():
    assert (HERE / "OWNER_WORD.md").exists(), "NIFTY 2023 is protected: the owner has not assigned it to this exam"
    fz = json.loads((HERE / "freeze-exam.json").read_text())
    assert set(fz["files"]) == set(FILES), "freeze must include OWNER_WORD.md"
    assert all(sha(HERE / f) == h for f, h in fz["files"].items()), "frozen files changed"
    assert not git("status", "--porcelain", "--", *FILES, "freeze-exam.json"), "freeze not committed"
    assert not (HERE / "exam2023-results.json").exists(), "scored once"
    binding = json.loads(BINDING.read_text())
    assert sha(SEALED) == binding["files_sha256"]["data.sqlite"], "sealed export changed"
    return fz


def tapes2023():
    return build_tapes(2023)


def build_tapes(year):
    """data.load_year's construction from the sealed export (no OI snapshots: no tested arm reads them).
    check() proves it on 2024 (seen) against data.load_year; only score() asks for 2023."""
    c = sqlite3.connect(SEALED.resolve().as_uri() + "?mode=ro", uri=True); c.row_factory = sqlite3.Row
    days = [r[0] for r in c.execute("SELECT DISTINCT substr(datetime,1,10) FROM candles WHERE datetime>=? AND datetime<? ORDER BY 1", (f"{year}-01-01", f"{year + 1}-01-01"))]
    tapes = []; coverage = []
    for day in days:
        assert day.startswith(str(year))
        rows = c.execute("SELECT * FROM candles WHERE datetime BETWEEN ? AND ? ORDER BY datetime", (day + " 09:15:00", day + " 15:29:00")).fetchall()
        opts = sorted({(r["strike"], r["opt"]) for r in rows if r["kind"] == "option"})
        if not opts:
            coverage.append(dict(day=day, contracts=0, status="NO_OPTIONS")); continue
        lookup = {v: j for j, v in enumerate(opts)}
        x = np.full((375, 4), np.nan); f = x.copy(); q = np.full((375, len(opts), 5), np.nan); bad = 0
        for r in rows:
            k = (int(r["datetime"][11:13]) - 9) * 60 + int(r["datetime"][14:16]) - 15
            if not 0 <= k < 375: continue
            vals = [r[n] for n in ("open", "high", "low", "close")]
            if not all(v is not None and np.isfinite(v) and v > 0 for v in vals) or not vals[2] <= min(vals[0], vals[3]) <= max(vals[0], vals[3]) <= vals[1]:
                bad += 1; continue
            if r["kind"] == "index": x[k] = vals
            elif r["kind"] == "future": f[k] = vals
            elif r["kind"] == "option":
                assert r["expiry"] == day
                if r["volume"] is None or r["volume"] < 0: bad += 1; continue
                q[k, lookup[r["strike"], r["opt"]]] = vals + [r["volume"]]
        now = [datetime.fromisoformat(day + "T09:15:00").replace(tzinfo=D.EP.IST) + timedelta(minutes=i + 1) for i in range(375)]
        tapes.append(D.Tape(day, x, f, q, np.array([k for k, o in opts]), np.array([1 if o == "CE" else -1 for k, o in opts]),
                            [f"NIFTY-{day}-{k:g}-{o}" for k, o in opts], now, np.arange(556, 931), bad))
        coverage.append(dict(day=day, contracts=len(opts), invalid_rows=bad, index_points=int(np.isfinite(x[:, 3]).sum()), future_points=int(np.isfinite(f[:, 3]).sum())))
    c.close()
    return tapes, coverage


# ---- coverage: unavailable is never zero (EXAM_E03_FAMILY.md) -------------------------------------------------
UNAVAILABLE = {}
ORIGINAL = E.directions


def available(t, i, d):
    c = float(t.close[i]); have = {float(k) for k, kind in zip(t.strikes, t.kinds) if kind == d}
    first = math.floor(c / 50) * 50 + 50 if d > 0 else math.ceil(c / 50) * 50 - 50
    need = [first + d * 50 * n for n in range(5) if 0 < d * (first + d * 50 * n - c) <= 200]
    return all(k in have for k in need)


def masked(t, rule):
    out = ORIGINAL(t, rule).copy()
    for i in np.flatnonzero(out):
        if not available(t, i, int(out[i])):
            UNAVAILABLE.setdefault(t.day, set()).add(int(i)); out[i] = 0
    return out


def random_directions(seed):
    def directions(t, rule):
        real = masked(t, rule)
        rng = random.Random(f"{seed}-{t.day}")
        lo, hi = int(np.searchsorted(t.minute, rule.start)), int(np.searchsorted(t.minute, rule.end))
        out = np.zeros(t.n, dtype=np.int8)
        for i in rng.sample(range(lo, hi), int(np.count_nonzero(real))):
            out[i] = rng.choice((1, -1))
        return out
    return directions


def clear():
    L.CACHE.clear(); N._DIR.clear()


# ---- arms -------------------------------------------------------------------------------------------------------
def arms():
    e03 = dict(max_lots=3, split=True, runner_floor=1.0, runner_keep=0.5, hero_target=9.0)
    return {
        "E02": ("x", X.Hero(**X.R3)),
        "E03": ("x", X.Hero(**{**X.R3, **e03})),
        "E031": ("r", R.E031),
        "E031_L8": ("r", replace(R.E031, chase=.08)),
        "E032": ("n", N.E032),
        "EN04_put2.5x": ("n", replace(N.E032, put_mult=2.5)),
        "EN04_put3x": ("n", replace(N.E032, put_mult=3.)),
        "EN04_put3.5x": ("n", replace(N.E032, put_mult=3.5)),
    }


def run(kind, tapes, rule, sc, details=False):
    clear()
    if kind == "x": return X.run_year(tapes, rule, sc, details)
    if kind == "r": return R.run(tapes, rule, sc, details)
    return N.run(tapes, rule, sc, details)


def brief(s):return {k: s[k] for k in ("net", "without_best", "worst", "drawdown", "trades", "profit_factor", "wins", "loss_days", "quarters", "fees")}


def score():
    fz = gate()
    E.directions = masked
    try:
        T, coverage = tapes2023()
        res = dict(freeze=fz, coverage=coverage, arms={}, tickets={})
        for name, (kind, rule) in arms().items():
            row = {}
            for sc in SC:
                r = run(kind, T, rule, sc, details=(sc == "ordinary"))
                row[sc] = brief(r["summary"])
                if sc == "ordinary":
                    res["tickets"][name] = [dict(day=p["day"], side="P" if p["direction"] < 0 else "C", lots=p["lots"], entry=p["entry"], net=p["net"],
                                                 exits=[e.get("reason") for e in p["events"][1:]]) for d in r["days"] for p in d["positions"]]
                if sc == "adverse":
                    row["skeptical"] = RD.bootstrap(RD.skeptical([d["net"] for d in r["days"]]), random.Random(RD.SEED))
            res["arms"][name] = row
            print(name, {sc: (row[sc]["net"], row[sc]["trades"]) for sc in SC}, flush=True)
        nets = []
        try:
            for s in range(SEEDS):
                E.directions = random_directions(s)
                nets.append(run("r", T, R.E031, "ordinary")["summary"]["net"])
        finally:
            E.directions = masked
        res["random_E031"] = dict(seeds=SEEDS, median=round(st.median(nets), 2), mean=round(st.mean(nets), 2),
                                  share_at_or_above=round(sum(n >= res["arms"]["E031"]["ordinary"]["net"] for n in nets) / SEEDS, 3))
        # EN03 lesson: put signals with efficiency in [0.65, 0.70) against those >= 0.70, each ticket on a fresh day book.
        loose = replace(N.E032, put_eff=.65); add = []; core = []
        for t in T:
            clear(); a = N.run_day(t, N.E032, "ordinary", details=True); clear(); b = N.run_day(t, loose, "ordinary", details=True)
            base = {(p["entry_i"], p["direction"]) for p in a["positions"]}
            add += [p["net"] for p in b["positions"] if (p["entry_i"], p["direction"]) not in base]
            core += [p["net"] for p in a["positions"] if p["direction"] < 0]
        res["en03_lesson"] = dict(added_put_tickets=len(add), added_mean=round(st.mean(add), 2) if add else None,
                                  core_put_tickets=len(core), core_mean=round(st.mean(core), 2) if core else None)
        res["unavailable_decisions"] = {d: len(v) for d, v in sorted(UNAVAILABLE.items())}
        A = res["arms"]; o, a_, sv = "ordinary", "adverse", "catastrophe"
        t = {}
        t["1_E031_stands"] = dict(ordinary=A["E031"][o]["net"] > 0, adverse=A["E031"][a_]["net"] > 0, without_best=A["E031"][o]["without_best"] > 0,
                                  worst=A["E031"][o]["worst"] >= -1250, above_random_median=A["E031"][o]["net"] > res["random_E031"]["median"])
        t["2_E031_vs_E03"] = dict(ordinary=A["E031"][o]["net"] >= A["E03"][o]["net"], adverse=A["E031"][a_]["net"] >= A["E03"][a_]["net"])
        t["3_L8_vs_E031"] = dict(severe_better=A["E031_L8"][sv]["net"] > A["E031"][sv]["net"], ordinary=A["E031_L8"][o]["net"] >= A["E031"][o]["net"],
                                 adverse=A["E031_L8"][a_]["net"] >= A["E031"][a_]["net"])
        t["5_E032_vs_E031"] = dict(ordinary=A["E032"][o]["net"] > A["E031"][o]["net"], adverse=A["E032"][a_]["net"] > A["E031"][a_]["net"],
                                   without_best=A["E032"][o]["without_best"] > A["E031"][o]["without_best"], worst=A["E032"][o]["worst"] >= 2 * A["E031"][o]["worst"])
        pe = [x["net"] for x in res["tickets"]["E031"] if x["side"] == "P"]; ce = [x["net"] for x in res["tickets"]["E031"] if x["side"] == "C"]
        t["6_asymmetry"] = dict(puts_per_ticket=round(st.mean(pe), 2) if pe else None, calls_per_ticket=round(st.mean(ce), 2) if ce else None,
                                holds=bool(pe and ce and st.mean(pe) > st.mean(ce)))
        t["7_E032_stands"] = dict(ordinary=A["E032"][o]["net"] > 0, adverse=A["E032"][a_]["net"] > 0, without_best=A["E032"][o]["without_best"] > 0,
                                  worst=A["E032"][o]["worst"] >= -2500)
        p3 = A["EN04_put3x"]; sk = p3["skeptical"]
        t["8_PUT3"] = dict(ordinary=p3[o]["net"] >= A["E032"][o]["net"], adverse=p3[a_]["net"] >= A["E032"][a_]["net"],
                           without_best=p3[o]["without_best"] >= A["E032"][o]["without_best"], loss_year=sk["loss_year_chance"] <= .30,
                           drawdown=sk["drawdown_p95"] <= 5000, severe=p3[sv]["net"] >= -6250,
                           neighbours_positive=all(A[k][s]["net"] > 0 for k in ("EN04_put2.5x", "EN04_put3.5x") for s in (o, a_)))
        res["tests"] = {k: dict(v, passed=all(x for x in v.values() if isinstance(x, bool))) for k, v in t.items()}
    finally:
        E.directions = ORIGINAL
    with (HERE / "exam2023-results.json").open("x", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2, default=str)
    print("TESTS", json.dumps({k: v["passed"] for k, v in res["tests"].items()}))


def check():
    """Machinery check on SEEN 2024: the loader equals data.load_year, and every arm runs under the coverage mask."""
    built, _ = build_tapes(2024); ref = X.tapes(2024)
    assert [t.day for t in built] == [t.day for t in ref]
    for a, b in zip(built, ref):
        assert np.array_equal(a.x, b.x, equal_nan=True) and np.array_equal(a.f, b.f, equal_nan=True) and np.array_equal(a.q, b.q, equal_nan=True)
        assert list(a.strikes) == list(b.strikes) and list(a.kinds) == list(b.kinds)
    E.directions = masked
    try:
        out = {name: run(kind, built, rule, "ordinary")["summary"]["net"] for name, (kind, rule) in arms().items()}
    finally:
        E.directions = ORIGINAL
    print("CHECK_OK loader == data.load_year on 2024;", out, "unavailable decisions 2024:", sum(len(v) for v in UNAVAILABLE.values()))


if __name__ == "__main__":
    {"freeze": freeze, "score": score, "check": check}[sys.argv[1]]()
