"""The sealed exam (PLAN.md): Yahoo broad panel 2019-04-01 .. 2022-12-30, opened once.

python exam.py freeze   -> writes freeze-exam.json (finalists, rule, source and data hashes)
python exam.py run      -> verifies the freeze, scores, writes exam-results.json
"""
from __future__ import annotations
import hashlib, json, random, statistics as st, sys
from copy import copy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab  # noqa: E402
import round2  # noqa: E402,F401  (registers night_screen)
from arms import MODELS, EXAM_START, EXAM_END  # noqa: E402

FINALISTS = {
    "BASE": lab.Arm("BASE"),                                         # shipped paper book (3 slots, risk plan)
    "TWO": lab.Arm("TWO", slots=2, sizing="equal"),
    "TWO_NIGHT": lab.Arm("TWO_NIGHT", slots=2, sizing="equal", select="night_screen", params=(("min", .001),)),
    "ONE": lab.Arm("ONE", slots=1, sizing="equal"),
}
PRIMARY_MODELS = ("E36", "PC")
STRESS_MODELS = ("E25", "E60")
YEARS = ("2019", "2020", "2021", "2022")
NULL_BOOKS = 200


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sources():
    files = [HERE / n for n in ("lab.py", "arms.py", "exam.py", "round2.py", "ev.py")]
    eng = [lab.ROOT / "python-engine" / n for n in ("penny_edge_engine.py", "penny_edge_backtest.py", "penny_risk.py", "config.py")]
    return {str(p.relative_to(lab.ROOT)).replace("\\", "/"): sha(p) for p in files + eng}


def freeze():
    out = HERE / "freeze-exam.json"
    if out.exists():
        raise SystemExit("freeze exists")
    f = {"frozen_at": datetime.now(timezone.utc).isoformat(), "window": [EXAM_START, EXAM_END],
         "finalists": {k: asdict(v) for k, v in FINALISTS.items()}, "primary_models": PRIMARY_MODELS,
         "stress_models": STRESS_MODELS, "bankroll": 25000.0, "compounding": "primary (as PLAN); fixed reported",
         "rule": ["closes >= 100, net > 0, ex_best > 0", "net > BASE net (same model)",
                  "peak-relative drawdown <= max(1.5 x BASE, 15%)", "net > 0 in >= 3 of 4 exam years",
                  f"net > 90th percentile of {NULL_BOOKS} random-order books from the same candidate pool, same slots and sizing"],
         "why_these": "R1: fewer equal positions win in every model/panel; R2/R3: EV model rejected (thin-name bounce), "
                      "night screen small but consistent; R4: genome search fails walk-forward, so no searched genome is a finalist.",
         "source": sources(), "days_yahoo_sha256": sha(HERE / "_local/days-yahoo.pkl")}
    out.write_text(json.dumps(f, indent=1))
    print("frozen", out)


def shuffled(days, seed):
    rng = random.Random(seed); out = []
    for d in days:
        nd = copy(d); cs = list(d.cands[:lab.RANK_DEPTH]); rng.shuffle(cs); nd.cands = cs; out.append(nd)
    return out


def run():
    f = json.loads((HERE / "freeze-exam.json").read_text())
    assert f["source"] == sources(), "source drift since freeze"
    assert f["days_yahoo_sha256"] == sha(HERE / "_local/days-yahoo.pkl"), "data drift since freeze"
    days = lab.load(HERE / "_local/days-yahoo.pkl")
    res = {"freeze": "freeze-exam.json", "opened_at": datetime.now(timezone.utc).isoformat(), "models": {}}
    for model in PRIMARY_MODELS + STRESS_MODELS:
        eb, xb = MODELS[model]
        m = res["models"][model] = {}
        for compound in (True, False):
            tag = "compound" if compound else "fixed"
            for name, a in FINALISTS.items():
                r = lab.run_book(days, replace(a, entry_bps=eb, exit_bps=xb, compound=compound), start=EXAM_START, end=EXAM_END,
                                 keep_trades=False)
                m.setdefault(tag, {})[name] = r["summary"]
        if model in PRIMARY_MODELS:
            nulls = {}
            for slots in (1, 2):
                nets = []
                for s in range(NULL_BOOKS):
                    a = replace(lab.Arm("NULL", slots=slots, sizing="equal"), entry_bps=eb, exit_bps=xb, compound=True)
                    nets.append(lab.run_book(shuffled(days, s), a, start=EXAM_START, end=EXAM_END, keep_trades=False)["summary"]["net"])
                q = sorted(nets)
                nulls[slots] = {"p50": q[NULL_BOOKS // 2], "p90": q[int(.9 * NULL_BOOKS)], "max": q[-1]}
            nulls[3] = None
            m["null_compound"] = nulls
            base = m["compound"]["BASE"]
            verdict = {}
            for name in ("TWO", "TWO_NIGHT", "ONE"):
                s = m["compound"][name]
                slots = FINALISTS[name].slots
                checks = {
                    "1_closes_net_exbest": s["n"] >= 100 and s["net"] > 0 and s["ex_best"] > 0,
                    "2_beats_base": s["net"] > base["net"],
                    "3_drawdown": s["dd_pct_peak"] <= max(1.5 * base["dd_pct_peak"], 15.0),
                    "4_years_positive": sum(s["by_year"].get(y, 0) > 0 for y in YEARS) >= 3,
                    "5_beats_null_p90": s["net"] > nulls[slots]["p90"],
                }
                verdict[name] = {"checks": checks, "pass": all(checks.values())}
            m["verdict"] = verdict
    (HERE / "exam-results.json").write_text(json.dumps(res, indent=1))
    for model, m in res["models"].items():
        for tag in ("compound", "fixed"):
            print(f"[{model} {tag}]")
            for name, s in m[tag].items():
                print(f"  {name:10s} n={s['n']:4d} net={s['net']:>11,.0f} exbest={s['ex_best']:>11,.0f} DD={s['dd_pct_peak']:5.1f}% "
                      f"pf={s['pf'] or 0:.2f} mean={s['mean_pct'] or 0:+.2f}% " + " ".join(f"{y}:{v:,.0f}" for y, v in s['by_year'].items()))
        if "verdict" in m:
            print(f"  null p90 (compound): 1 slot {m['null_compound'][1]['p90']:,.0f}  2 slots {m['null_compound'][2]['p90']:,.0f}")
            for name, v in m["verdict"].items():
                print(f"  VERDICT {model} {name}: {'PASS' if v['pass'] else 'FAIL'} {v['checks']}")


if __name__ == "__main__":
    {"freeze": freeze, "run": run}[sys.argv[1]]()
