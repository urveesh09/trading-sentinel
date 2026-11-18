"""Reconcile archived claims, not a new strategy score or parameter selection."""
from pathlib import Path
from collections import Counter
import json
import sys

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / '2026-11-18-expiry-en96'
sys.dont_write_bytecode = True
sys.path.insert(0, str(OLD))
import round8
import families9 as F


def main():
    r = json.loads((OLD/'results9.json').read_text())
    a = json.loads((OLD/'anatomy9.json').read_text())
    p = json.loads((OLD/'post9.json').read_text())
    out = dict(scope='archived evidence reconciliation; no new score',
        registry=F.counts(F.registry()), scored=r['dedup_counts'],
        champions=r['champions'], labels=r['labels'],
        random_retention=r['diagnostics']['EN96_random_retention'],
        extension=p['EN98_extension_at_EN87_events_ATR10_units'],
        fast_opposition=p['EN102_min_signed_S15_fixed_basket_during_EN87_holds'])
    out['inner_constraint_counts'] = {}
    for fam in [f'EN{x}' for x in range(96, 111) if x != 105]:
        rows = [x for k, v in a['stageb'][fam].items() if k != '197' for x in v]
        counts = Counter(c for x in rows for c, v in x['checks'].items() if not v)
        out['inner_constraint_counts'][fam] = dict(records=len(rows), failures=dict(counts),
            pass_all=sum(x['passed'] for x in rows),
            support_only_failure=sum(not x['checks']['support'] and all(v for c, v in x['checks'].items() if c != 'support') for x in rows))
    out['promising_cells'] = {}
    for fam in ('EN96', 'EN100', 'EN101', 'EN110'):
        rows = [(k, v) for k, v in r['configs'].items() if k.endswith('|NIFTY') and v['family'] == fam and v['kind'] == 'CELL']
        k, v = max(rows, key=lambda kv: kv[1]['adverse']['net'])
        out['promising_cells'][fam] = dict(id=k, settings=v['settings'], ordinary=v['ordinary'], adverse=v['adverse'], wallet=v['wallet'])
    out['source_gate_defect'] = dict(case='SOURCES/VOTE2',
        needs_oi_reported=F.Spec(signal='SOURCES', sources='VOTE2').needs_oi(),
        expected_under_IMPl9_sensex_contract=True,
        note='VOTE2 needs a typed dependency declaration; archived SENSEX cells have zero trades')
    assert not out['source_gate_defect']['needs_oi_reported']
    for row in out['promising_cells'].values():
        key = row['id']; days = a['days'][key]
        assert abs(sum(days['ordinary']) - row['ordinary']['net']) < .02
        assert abs(sum(days['adverse']) - row['adverse']['net']) < .02
    assert len(r['configs']) == 304 and not r['champions']
    (HERE/'claims10.json').write_text(json.dumps(out, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(constraints=out['inner_constraint_counts'],
        source_gate=out['source_gate_defect'],
        promising={k: dict(id=v['id'], ordinary=v['ordinary']['net'], adverse=v['adverse']['net']) for k,v in out['promising_cells'].items()}), indent=2))


if __name__ == '__main__':
    main()
