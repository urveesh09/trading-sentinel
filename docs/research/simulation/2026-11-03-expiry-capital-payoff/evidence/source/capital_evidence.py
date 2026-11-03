"""Unmodified simulation skill receipts for separate capital/payoff research books."""
from pathlib import Path
from datetime import date,timedelta
import importlib.util,json,shutil,sys
import ledger_guard as G
HERE,ROOT=G.HERE,G.ROOT
sha=G.sha

def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def helper():
    p=ROOT/'.agents/skills/sentinel-trading-simulation/scripts/simulation_evidence.py'
    spec=importlib.util.spec_from_file_location('capital_stock_helper',p)
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);return h

def main():
    G.verify();assert not G.git('diff','HEAD','--','python-engine').strip()
    h=helper();out=HERE/'evidence'
    sources=('ledger-results.json','credit-results.json','hybrid-results.json','unbraked-results.json')
    raw={n:json.loads((HERE/n).read_text()) for n in sources};specs={}
    for source,names in [('ledger-results.json',('E031','NET_RISK_LEDGER','PROFIT_REENTRY')),
        ('credit-results.json',('CREDIT_8M','CREDIT_TREND')),('hybrid-results.json',('HYBRID_8M','HYBRID_TREND')),
        ('unbraked-results.json',('HYBRID_8M','HYBRID_TREND','CREDIT_8M','CREDIT_TREND'))]:
        for name in names:
            for sc in ('ordinary','adverse','catastrophe'):
                prefix='expiry_unbraked_' if source.startswith('unbraked') else 'expiry_'
                specs[prefix+name.lower()+'_'+sc]=(source,f'{name}|continuous|{sc}')
    modules=[*specs,'expiry_sensex_unavailable']
    h.initialize(ROOT,ROOT.parent/'Production_Trading-sentinel',out,'2024-01-01','2025-12-31','2026-11-03',modules)
    initial=json.loads((HERE/'initial.json').read_text());proof={}
    for y,want in initial['data'].items():
        p=HERE.parent/f'2026-11-03-expiry-e02/_local/{y}.sqlite';assert sha(p)==want
        proof[str(p.resolve())]=dict(sha256=want,verified_current_sha256=sha(p))
    sys.path.insert(0,str(ROOT/'python-engine'))
    import expiry_paper as EP
    from config import settings
    fee=EP.fee_schedule('NFO')
    prior=json.loads((HERE.parent/'2026-11-03-expiry-e032-structure/audit-results.json').read_text())['native_fee_snapshot']
    assert fee==prior
    dump(out/'data-proof.json',dict(files=proof,api_calls=0,year2023_read=False,
      caveat='Raw selected-year DBs remain ignored local dependencies outside the receipt folder; full bytes verified before sealing'))
    dump(out/'configuration.json',dict(classification='SEEN_2024_2025_NO_QUALIFICATION',own_cash=25000,normalized_lot=65,
      native_fee_snapshot=fee,native_fees='Current normalized schedule; not actual historical tax/lot returns',
      observed_dev_switches={k:bool(getattr(settings,k)) for k in ('EXPIRY_E02_SHADOW_ENABLED','EXPIRY_E03_SHADOW_ENABLED','EXPIRY_E031_SHADOW_ENABLED')},
      baseline_ticket=1250,baseline_day=2500,credit_day=5000,brakes=[1500,3000,4000],slots='Original 2; ledger alternatives may repeat causally',
      credit_cash='Full width plus one point and fee buffer 500; actual broker SPAN/ELM and atomic basket fills unavailable',
      universe='105 selected NIFTY expiry days in 2024/2025; 4-step strike limit; no SENSEX/full 2026-chain qualification',
      fill_basis='Completed-bar decisions, next executable bar, estimated spread and 20% bar-volume proxy; separate ordinary/adverse/severe',
      cash_basis='Each arm own cash; continuous book separately from reset-year experiments; no shared Sentinel profit',
      residual_basis='Short unclosed halts future; fully funded unsold long hedge conservative zero lower bound with assumed writeoff separate',
      before_score_commits=['f34ceb9','ff34d6b','2d0fe98','698a128'],
      primary_verdicts=json.loads((HERE/'decisions.json').read_text()),enabled=False,deployed=False,runtime_changed=False,selected_candidate=None))
    inputs=['configuration.json','data-proof.json']
    for p in sorted(HERE.glob('*.py')):
        n='source/'+p.name;target=out/n;target.parent.mkdir(exist_ok=True);shutil.copyfile(p,target);inputs.append(n)
    for n in ('PLAN.md','CREDIT.md','HYBRID.md','DIAGNOSTICS.md','initial.json','freeze-ledger.json','freeze-credit.json',
              'freeze-hybrid.json','freeze-diagnostics.json','freeze-diagnostics-draft.json','freeze-audit-v2.json'):
        shutil.copyfile(HERE/n,out/n);inputs.append(n)
    h.seal(out,inputs)
    artifacts=['analysis.md','verification.json','audit-results.json','diagnostic-audit.json','decisions.json',
       'daily-results.csv','trades.csv','loss-attribution.json','audit-failure.json','diagnostics.json',*sources]
    shutil.copyfile(ROOT/'docs/EXPIRY_RESEARCH_CAPITAL_PAYOFF.md',out/'analysis.md')
    for n in artifacts[1:]:shutil.copyfile(HERE/n,out/n)
    dates=[];dt=date(2024,1,1)
    while dt<=date(2025,12,31):dates.append(dt.isoformat());dt+=timedelta(days=1)
    empty={k:None for k in ('closed_trades','signals','filled_fee_pnl','assumed_pnl','modeled_net','unresolved')}
    limitations=['Both years repeatedly seen; no fresh qualification','Current lot/fees normalized, not historical realizable returns',
      'No historical executable depth, queue, atomic basket or broker margin proof',
      'Unknown dates unavailable, not flat zero; independent arms are not unified system profit',
      'Complete-bar estimates cannot qualify instant execution or guaranteed stop prices']
    for module,(source,key) in specs.items():
        run=raw[source]['runs'][key];known={d['day']:d for d in run['days']}
        def money(d):
            assumed=d.get('assumed',0.);filled=d.get('filled_fee',round(d['net']-assumed,2))
            return dict(closed_trades=d['trades']-d['unresolved'],signals=None,filled_fee_pnl=filled,assumed_pnl=assumed,
              modeled_net=d['net'],unresolved=d['unresolved'],residual_long_assets=d.get('residual_longs',0))
        daily=[]
        for day in dates:
            d=known.get(day)
            daily.append(dict(date=day,status='PARTIAL' if d else 'UNAVAILABLE',metrics=money(d) if d else empty.copy(),
              reason='Known selected expiry minute-bar experiment; zero means no model entry' if d else 'No assessed selected expiry tape / unavailable after liability; not a zero PnL day'))
        metrics=money(run['summary']);assert metrics['unresolved']==0 and metrics['residual_long_assets']==0
        dump(out/'modules'/(module+'.json'),dict(module=module,start=dates[0],end=dates[-1],status='PARTIAL',
          fidelity='BAR_LIFECYCLE',population='SHADOW',coverage='PARTIAL',metrics=metrics,daily_results=daily,inputs=inputs,artifacts=artifacts,
          reason=f'{source} / {key}; all six new primary alternatives rejected; no native candidate',
          assumptions=['Own-cash book continuous on stated calendar','Completed-bar decisions, later fills, all native fees',
            'Credit/hybrid broker execution and actual margin unqualified'],limitations=limitations))
    module='expiry_sensex_unavailable'
    dump(out/'modules'/(module+'.json'),dict(module=module,start=dates[0],end=dates[-1],status='UNAVAILABLE',fidelity='NONE',
      population='SHADOW',coverage='UNAVAILABLE',reason='No qualified full SENSEX chain/policy in this NIFTY-only frozen set; no new acquisition',
      metrics=empty.copy(),daily_results=[],inputs=inputs,artifacts=artifacts,assumptions=[],limitations=['SENSEX not inferred from NIFTY or opening-ATM bars']))
    assert not h.render(out)['errors'];assert not h.verify(out)
    print('CAPITAL_STOCK_RECEIPTS_VERIFIED',len(modules),'modules; no candidate or qualification')

if __name__=='__main__':main()
