"""Create the durable preferred reference from exact committed N03 evidence."""
import hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];ROOT=next(p for p in HERE.parents if (p/'python-engine').is_dir());OLD=HERE.parent/'2026-11-01-fno-eff-improvement'
load=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def run():
    target=ROOT/'docs/FNO_RESEARCH_REFERENCE.json';assert not target.exists(),'do not silently replace existing reference'
    results=load(OLD/'results.json');freeze=load(OLD/'freeze.json');name='NORMAL|TPB_ONE|RETEST';years={};book=freeze['books'][name]
    for y in ('2024','2025','2026'):
        key=load(OLD/f'_local/keys-{y}.json')[name];p=OLD/'_local/evals'/f'{key}.json';obj=load(p);assert obj['book']==book
        net=sum(t['net_pnl'] for t in obj['trades']);assert round(net)==results['books'][name]['years'][y]['net']
        years[y]={'evaluation':p.relative_to(ROOT).as_posix(),'evaluation_sha256':sha(p),'net_exact':net,**results['books'][name]['years'][y]}
    record={'schema':'sentinel_preferred_research_reference_v1','preferred_id':'BALANCED_RETEST_N03','label':'Preferred balanced seen-data research reference',
        'selection_context':'Owner requested persistence after N03; balanced annual net and lower drawdown, not universal dominance or a frozen acceptance pass.',
        'status':'RESEARCH_UNQUALIFIED_NOT_DEPLOYED','study':OLD.relative_to(ROOT).as_posix(),'book_key':name,'book':book,
        'source_commit':'2de5448148e76cdbafcc24168489adf7624e51dd','results_commit':'4a90fdcb4765962f262c9a1597991109d9b84f1f','handoff_commit':'cee22048710f5cbb32e4864c26d034fe2103a36d',
        'freeze_sha256':sha(OLD/'freeze.json'),'results_sha256':sha(OLD/'results.json'),'years':years,'capital':'fresh250000 each year','cost':'current fees/modeled adverse quotes + (200+5*lots)*lots',
        'risk':'normal2/3 lots, only low-day TPB additions1lot; all brakes/exits/hard-flat; normalized lot65','scope':'NIFTY single-leg only;2026 through October28',
        'limitations':['All test years already studied; no fresh profitability qualification.','Does not beat unchanged benchmark in2026 and paired statistical bar fails.','Modeled historical quotes, current fees/lot normalization, known gaps/negative-volume and depth/regime limits.','Independent annual accounts, not continuous three-year wealth.'],
        'comparison_controls':['Unchanged MAIN','Unchanged TPB_ONE','Original TPB_FULL','N02 CORE_SELECT','N03 combined HORIZON'],
        'replacement_rule':'Keep this immutable preferred identity until a later explicit versioned comparison decision; do not silently substitute highest seen total or relax failed tests.',
        '2023':'deferred option exam; untouched','can_place_orders':False,'qualified':False,'deployed':False}
    target.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    text='''# F&O research reference — read before continuing

**Preferred balanced research reference: `BALANCED_RETEST_N03`.**

This is MAIN + one-lot LOW-day TPB puts + EFF retest entries. It is the owner's
preferred balanced comparison from the already-studied2024–2026 tests, not a
qualified or deployed strategy and not best on every metric. Preserve this
identity across compaction, new sessions and agent handoffs.

| Year | Modeled net after costs | Closed-cash drawdown | Trades |
|---|---:|---:|---:|
'''
    for y,v in years.items():text+=f"| {y}{' to Oct28' if y=='2026' else ''} | Rs{v['net']:+,} | {v['fall_pct']:.2%} | {v['trades']} |\n"
    text+='''
FreshRs250,000 per year, normalized65-unit lots, normal2-lot/3-when-proven caps;
ONLY low-day TPB additions are one lot. Net includes modeled adverse quotes,
current shipped fees and extra(200+5*lots)*lots stress in the cash path. These
are independent NIFTY single-leg accounts, not whole-system or continuous wealth.

Exact identity is in [FNO_RESEARCH_REFERENCE.json](FNO_RESEARCH_REFERENCE.json):
source2de5448, results4a90fdc, handoffcee2204, N03 book key
`NORMAL|TPB_ONE|RETEST`, freeze/result/evaluation hashes and the complete book.
See [N03 findings](research/simulation/2026-11-01-fno-eff-improvement/README.md).

It is more balanced on these seen years but gives up2026 profit against its
unchanged benchmark and fails paired significance; do not call it qualified.
Keep MAIN, TPB_ONE, TPB_FULL and N02 selector comparisons visible. Do not replace
this reference silently after a higher-total but less consistent trial. A later
replacement needs a versioned decision with its own explicit rule and evidence.

Current next round: N04 separates early30-minute departure from conditional
90-minute continuation with no new thresholds. Preserve this reference unchanged
and compare every new result against it.2023 option exam remains deferred and
unscored. No application/Production/money/order/message activation is authorized
by a research score. Prospective evidence remains necessary.
'''
    (ROOT/'docs/FNO_RESEARCH_REFERENCE.md').write_text(text,encoding='utf-8');print('REFERENCE_RECORDED',record['preferred_id'])
if __name__=='__main__':run()
