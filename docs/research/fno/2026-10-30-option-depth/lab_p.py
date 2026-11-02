"""O30p: option-depth offspring of TPB and the best blend, research only.

Hypothesis: option choice, not another market filter, may improve the trade's
participation in slow moves. Compare absolute target delta 0.40 / 0.65 / 0.75
against the unchanged 0.55 parents. Actual archived contracts only; no new
expiry data, option theory fills, safety relaxation or Production changes.
"""
from __future__ import annotations
import argparse,json,os,shutil,subprocess,sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'python-engine/fno_policy_replay.py').is_file())
sys.path.insert(0,str(ROOT/'docs/research/fno/2026-10-30-micro-adaptation'))
import lab_n as N
C,Y,G,O27F=N.C,N.Y,N.G,N.O27F
LOCAL=HERE/'_local';Y.EVALS=LOCAL/'evals'
from config import settings
_entry_before=Y.BookReplay._entry

def entry(self,book,obs,frame,day,now):
    original=settings.FNO_TARGET_DELTA
    try:
        settings.FNO_TARGET_DELTA=self.book.get('target_delta',original)
        return _entry_before(self,book,obs,frame,day,now)
    finally:
        settings.FNO_TARGET_DELTA=original

Y.BookReplay._entry=entry

def books():
    parents=N.books()
    out={n:parents[n] for n in ('REF|LIVE','REF|BEST','REF|TPB')}
    for parent in ('TPB','BEST'):
        for delta in (.40,.65,.75):
            out[f'P|{parent}|D{round(delta*100)}']={**parents['REF|'+parent],'target_delta':delta}
    out.update({n:b for n,b in parents.items() if n.startswith('NULL')})
    return out

RULE={
 'question':'Does option delta choice improve the robust entry/exits, rather than another day filter?',
 'candidates':6,'delta_targets':[.40,.65,.75],'baseline_target':.55,
 'pass':'beat OWN parent in BOTH years, >=40 trades/year, positive without best day, positive after 200/trade; '
        'drawdown <=1.25 parent; not worse in >=3 of 4 halves; beat random median; no unresolved positions',
 'selection':'per parent choose variant by worst stressed half on one year, score on other, both ways',
 'status':'both years seen; no retuning; 2024 existing exam unchanged; no qualification or deployment',
 'limitations':'target delta is a preference subject to available near-weekly strikes and shipped plan gates; '
               'no guarantee a 12500 cash account can afford the selected option; exact one-lot replay still required'}

def bindings():
    b = N.bindings()
    for name in ("lab_p.py", "analyze_p.py", "test_lab_p.py"):
        p = HERE / name
        b["sources"][p.relative_to(ROOT).as_posix()] = Y.grid._sha(p)
    return b


def freeze():
    parts = {}
    for year in ("2025", "2026"):
        raw = subprocess.check_output([sys.executable, str(HERE / "lab_p.py"), "bindings"], cwd=ROOT,
                                      env={**os.environ, "O30C_YEAR": year})
        parts[year] = json.loads(raw.decode().strip().splitlines()[-1])
    Y.write_new(HERE / "freeze.json", {"schema": "o30p_option_depth_v1", "bindings": parts, "books": books(),
                                       "rule": RULE, "can_place_orders": False})
    print("FROZEN", len(books()), "books x 2 years")


def run(jobs):
    frozen = json.loads((HERE / "freeze.json").read_text())
    assert frozen["bindings"][C.YEAR] == json.loads(json.dumps(bindings(), default=str)), "inputs changed"
    rel = (HERE / "freeze.json").relative_to(ROOT).as_posix()
    assert frozen == json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)), "not committed"
    assert 1 <= jobs <= 2
    O27F.deny_network()
    all_books = books()
    Y.EVALS.mkdir(parents=True, exist_ok=True)
    dirs = [ROOT / f"docs/research/fno/{s}/_local/evals" for s in (
        "2026-10-30-day-router", "2026-10-30-case-study", "2026-10-30-nifty-2025-test",
        "2026-10-29-year-genome")]
    for n, b in all_books.items():
        if not n.startswith(("REF", "NULL")):
            continue
        key = Y.task_key(b, "year", C.WINDOW) + ".json"
        src = next((d / key for d in dirs if (d / key).is_file()), None)
        if src and not (Y.EVALS / key).exists():
            shutil.copyfile(src, Y.EVALS / key)
    C.table("year")
    with ProcessPoolExecutor(max_workers=jobs, initializer=C._init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(all_books.values()), source="year", window=C.WINDOW)
    Y.write_new(LOCAL / f"results-raw-{C.YEAR}.json", {"freeze_sha256": Y.grid._sha(HERE / "freeze.json"),
        "year": C.YEAR, "books": {n: Y.task_key(b, "year", C.WINDOW) for n, b in all_books.items()},
        "trades": runner.trades})
    print("DONE", C.YEAR, len(runner.trades), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["bindings", "freeze", "run"])
    cli.add_argument("--jobs", type=int, default=2)
    a = cli.parse_args()
    if a.action == "bindings":
        print(json.dumps(bindings(), default=str))
    else:
        {"freeze": freeze, "run": lambda: run(a.jobs)}[a.action]()
