"""N06 offline saved-policy selection. No application imports this module."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from dataclasses import replace
from concurrent.futures import ProcessPoolExecutor

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'python-engine').is_dir())
PARENT = HERE.parent / '2026-11-01-fno-stall-refinement'
sys.path[:0] = [str(HERE), str(PARENT)]
import refine_lab as P
import variant_policy as R
Y, B, C, X = P.Y, P.B, P.C, P.X
OLD = P.LOCAL
LOCAL = HERE / '_local'
P.LOCAL = LOCAL
P.P.LOCAL = LOCAL
P.P.E.LOCAL = LOCAL
X.LOCAL = LOCAL
Y.EVALS = LOCAL / 'evals'
_MODELS = None


def decision(self, day):
    global _MODELS
    policy = self.book.get('n06_policy')
    if policy == 'STATIC':
        return dict(variant=self.book['n06_variant'], asof=None, latest_label_exit=None)
    if _MODELS is None:
        _MODELS = json.loads((LOCAL / f'decisions-{B.YEAR}.json').read_text())
    d = copy.deepcopy(_MODELS[policy][day])
    if d['variant'] not in R.ORDER or d['asof'] != day or (d['latest_label_exit'] and d['latest_label_exit'][:10] >= day):
        raise ValueError('missing, unknown or noncausal entry decision')
    return d


_entry = Y.BookReplay._entry
_route = Y.BookReplay.route


def route(self, frame, regime, now):
    if self.book.get('n06_policy') not in (None, 'STATIC'):
        from datetime import datetime, timedelta
        bar = Y.replay._last_closed_bar(frame, now)
        if bar is None or now - (datetime.fromisoformat(bar).replace(tzinfo=now.tzinfo) + timedelta(minutes=5)) >= timedelta(minutes=5):
            return X.G.MomSignal(bar_ts=bar or '', reject_reason='n06:stale_or_missing_bar')
    return _route(self, frame, regime, now)


Y.BookReplay.route = route


def entry(self, book, obs, frame, day, now):
    if not self.book.get('n06_policy'):
        return _entry(self, book, obs, frame, day, now)
    # Never borrow yesterday's decision if today's decision is unavailable.
    try:
        d = decision(self, now.date().isoformat())
    except (KeyError, FileNotFoundError, ValueError):
        self.notes['n06_decision_unavailable'] += 1
        return
    variant = d['variant']
    scope = (now.date().isoformat(), variant)
    if getattr(self, '_n06_scope', None) != scope:
        self._n03_retest = P.P.E.R.RetestState()
        self._n03_context = None
        self._n06_scope = scope
    original = self.book
    identity = Y.digest(original)
    before = book.next_id
    trace_start = len(getattr(self, 'decisions', []))
    # Routing flags are temporary; task/config hashes always use original book.
    self.book = {**original, 'n02_profile': 'MAIN' if variant == 'MAIN' else 'TPB_ONE',
                 'n03_variant': 'BASE' if variant == 'MAIN' else 'RETEST'}
    try:
        _entry(self, book, obs, frame, day, now)
        for trace in getattr(self, 'decisions', [])[trace_start:]:
            trace.update(n06_variant=variant, n06_policy=original['n06_policy'], n06_decision=copy.deepcopy(d))
        if book.next_id != before:
            leg = book.open[before]
            leg._n06_decision = copy.deepcopy(d)
            leg._n02_metadata.update(admission_id=f'N06/{B.YEAR}/{identity}/{before}',
                n06_variant=variant, n06_policy=original['n06_policy'], n06_decision=copy.deepcopy(d),
                n05_mode='BASE' if variant == 'MAIN' else variant)
    finally:
        self.book = original


Y.BookReplay._entry = entry
_manage = Y.BookReplay._manage


def manage(self, book, obs, now):
    if not self.book.get('n06_policy'):
        return _manage(self, book, obs, now)
    full, policies = book.open, self.policies
    try:
        for ident in sorted(full):
            leg = full[ident]
            mode = leg._n02_metadata['n06_variant']
            if mode not in R.ORDER:
                raise ValueError('unknown admitted exit policy')
            i = self.leg_member[ident]
            book.open = {ident: leg}
            self.policies = list(policies)
            if self.members[i]['name'] == 'EFF' and mode not in ('BASE', 'MAIN'):
                minute, ctx = P.review(leg, obs, now, self._frame, mode)
                leg._n05_exit_context = ctx
                params = {**dict(policies[i].exit_overrides), 'FNO_TIME_STOP_MIN': minute}
                self.policies[i] = replace(policies[i], exit_overrides=tuple(sorted(params.items())))
            # Global n05_mode stays BASE: only this leg's frozen policy overrides.
            _manage(self, book, obs, now)
            if ident not in book.open:
                del full[ident]
    finally:
        book.open, self.policies = full, policies


Y.BookReplay._manage = manage
Y.KEEP = tuple(dict.fromkeys((*Y.KEEP, 'n06_variant', 'n06_policy', 'n06_decision')))


def books(phase):
    variants = R.ORDER if phase == 'reference' else ('MAIN_ANCHOR', 'STRUCT_ANCHOR')
    out = {}
    for name in variants:
        b = X.book('N06|' + name, 'STATIC', 'MAIN' if name == 'MAIN' else 'TPB_ONE')
        b.update(n03_variant='BASE', n03_context='N06', n03_sizing='NORMAL', n03_contract='v1',
                 n04_mode='BASE', n04_context='N06', n04_contract='v1', n05_mode='BASE',
                 n05_context='N06', n05_contract='v1', n06_policy='STATIC' if phase == 'reference' else name,
                 n06_variant=name if phase == 'reference' else None, n06_contract='v1')
        out[name] = b
    return out


def reference_files():
    out = {}
    for y in ('2024', '2025', '2026'):
        keys = json.loads((OLD / f'keys-{y}.json').read_text())
        out[y] = {v: OLD / 'evals' / (keys['NORMAL|' + ('MAIN|BASE' if v == 'MAIN' else 'BALANCED_RETEST|' + v)] + '.json') for v in R.ORDER}
    return out


def bindings():
    out = P.bindings()
    for p in [*HERE.glob('*.py'), HERE/'PLAN.md', HERE/'configuration.json']:
        out['sources'][p.relative_to(ROOT).as_posix()] = B.P.sha(p)
    out['n05_freeze_sha256'] = B.P.sha(PARENT/'freeze.json')
    out['n05_results_sha256'] = B.P.sha(PARENT/'results.json')
    out['n05_controls'] = {p.relative_to(ROOT).as_posix(): B.P.sha(p) for fs in reference_files().values() for p in fs.values()}
    out['saved_checkpoints'] = {p.name:B.P.sha(p) for stem in ('FNO_RESEARCH_REFERENCE','FNO_RESEARCH_CHALLENGERS','FNO_RESEARCH_PROGRESS') for p in (ROOT/'docs').glob(stem+'.*')}
    return out


def verify(phase):
    f = json.loads((HERE/'freeze.json').read_text())
    assert f['bindings'][B.YEAR] == X.native(bindings()), 'source/input/reference changed'
    for name in ['freeze.json'] + (['decision-manifest.json'] if phase == 'candidate' else []):
        p = HERE/name
        assert json.loads(subprocess.check_output(['git','show','HEAD:'+p.relative_to(ROOT).as_posix()],cwd=ROOT)) == json.loads(p.read_text()), 'uncommitted '+name
    if phase == 'candidate':
        m = json.loads((HERE/'decision-manifest.json').read_text())
        assert B.P.sha(LOCAL/f'decisions-{B.YEAR}.json') == m['decisions'][B.YEAR]['sha256']
        assert all(B.P.sha(ROOT/p)==h for p,h in m['reference_files'].items())


def freeze():
    clean = {k:v for k,v in os.environ.items() if k not in ('O30F_YEAR','O30C_YEAR')}
    out = {}
    for y in ('2024','2025','2026'):
        env = {**clean, **({'O30F_YEAR':y} if y=='2024' else {'O30C_YEAR':y})}
        out[y] = json.loads(subprocess.check_output([sys.executable,__file__,'bindings'],cwd=ROOT,env=env).decode().strip().splitlines()[-1])
    assert not (HERE/'freeze.json').exists()
    X.write(HERE/'freeze.json',dict(schema='n06_variant_v1',bindings=out,reference_books=books('reference'),candidate_books=books('candidate'),configuration=json.loads((HERE/'configuration.json').read_text()),qualified=False,can_place_orders=False,all_years_seen=True))


def run(jobs, phase):
    assert 1 <= jobs <= 3
    B.O27F.deny_network()
    verify(phase)
    C.table('year')
    with ProcessPoolExecutor(max_workers=jobs, initializer=B.L._init) as pool:
        Y.Runner(pool,jobs).run(list(books(phase).values()),source='year',window=C.WINDOW)
    verify(phase)
    X.write(LOCAL/f'keys-{phase}-{B.YEAR}.json',{n:Y.task_key(b,'year',C.WINDOW) for n,b in books(phase).items()})
    print('DONE',phase,B.YEAR,len(books(phase)),flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['bindings','freeze','run'])
    p.add_argument('--phase', choices=['reference','candidate'], default='reference')
    p.add_argument('--jobs',type=int,default=3)
    a = p.parse_args()
    if a.action == 'bindings': print(json.dumps(X.native(bindings())))
    elif a.action == 'freeze': freeze()
    else: run(a.jobs,a.phase)
