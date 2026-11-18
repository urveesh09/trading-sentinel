"""Proposal manifest/links checker. No strategy/data score and no network."""
from pathlib import Path
import hashlib
import itertools
import json
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SPEC = ROOT / 'docs/EXPIRY_RESEARCH_EN111_EN120.md'
GRIDS = [
 ('EN111', dict(contract=['LEGACY_UP_TO_3','NEARER_ONE_LOT'], target=[1,1.25,1.5], hold=[8,10,12])),
 ('EN112', dict(context=['EXTENSION_RANK','ACCELERATION','BOTH'], assignment=['FRESH_GETS_ROOM','MATURE_GETS_ROOM'], profile=['TARGET_ONLY','HOLD_ONLY','BOTH'])),
 ('EN113', dict(lag=[1,3,5], percentile=[80,90], response=['DENY_EXTENSION','EXIT_WITH_GIVEBACK'])),
 ('EN114', dict(activity=[4,8,12], wall=[8,12,16], scope=['BASE_ONLY','BASE_AND_RUNNER'])),
 ('EN115', dict(window=[20,40,60], ridge=[1,10], residual_penalty=[0,1])),
 ('EN116', dict(states=[2,3], refit=[1,5], persistence=['IMMEDIATE','TWO_BAR_HYSTERESIS'])),
 ('EN117', dict(excursion=[0,.25], target=['MIDPOINT','OPPOSITE_QUARTILE'], stop_buffer=[.25,.5], cost_coverage=[1,2])),
 ('EN118', dict(learner=['RIDGE','STUMP'], regularization=['LIGHT','HEAVY'], k=[0,1,2])),
 ('EN119', dict(wait_seconds=[1,3], urgency=[1,2], ceiling=[1.02,1.04,1.08])),
 ('EN120', dict(depth=[1,2], refit=[5,20], switch_margin=[0,.1,.25])),
]


def main():
    families = []
    for slot, axes in GRIDS:
        cells = [dict(id=f'{slot}:{i:04d}', settings=dict(zip(axes, values)))
                 for i, values in enumerate(itertools.product(*axes.values()), 1)]
        families.append(dict(slot=slot, axes=axes, count=len(cells), cells=cells,
            fidelity='PACKET_SOURCE_GATED' if slot=='EN119' else 'BAR_POLICY_PROPOSAL'))
    ids = [c['id'] for f in families for c in f['cells']]
    assert len(ids) == len(set(ids)) == 138
    assert sum(f['count'] for f in families if f['slot']!='EN119') == 126
    text = SPEC.read_text(encoding='utf-8')
    assert all(text.count('## '+s+' -') == 1 for s,_ in GRIDS)
    checked = []
    for doc in (SPEC, HERE/'REVIEW10.md', HERE/'SOURCES10.md', HERE/'PLAN10.md', HERE/'STATUS10.md'):
        for rel in re.findall(r'`([^`]+\.md)`', doc.read_text(encoding='utf-8')):
            if rel.startswith(('research/', '../../../')):
                target = (doc.parent/rel).resolve()
                assert target.exists(), (doc, rel)
                checked.append(str(target.relative_to(ROOT)))
    manifest = dict(status='PROPOSAL_ONLY_NOT_A_SCORE_FREEZE', policy_cells=138,
        bar_cells=126, packet_cells=12, spec_sha256=hashlib.sha256(SPEC.read_bytes()).hexdigest(),
        note='Controls/ablations and capability sets must be expanded in developer IMPL10 before scoring.', families=families)
    (HERE/'families10-proposed.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    receipt = dict(status='PASS', policy_cells=138, unique_ids=True, local_links=checked,
        strategy_scored=False, historical_results_edited=False, production_edited=False)
    (HERE/'proposal-verification10.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(receipt))


if __name__=='__main__':
    main()
