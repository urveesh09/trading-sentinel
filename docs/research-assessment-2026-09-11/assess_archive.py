import json,gzip,hashlib,math,collections,sqlite3
from pathlib import Path
from datetime import datetime,timedelta,timezone
ROOT=Path('/data/research')
def ts(v): return datetime.fromisoformat(v.replace('Z','+00:00'))
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
masters={}; files=[]; master_results=[]
for p in ROOT.glob('contract-masters/**/manifest.json'):
 m=json.loads(p.read_text());raw=p.parent/'raw.csv'; contracts=p.parent/'contracts.jsonl'
 idx={str(x['instrument_token']):x for x in map(json.loads,contracts.read_text().splitlines())}
 day=p.parent.parent.name;exchange=p.parent.parent.parent.name
 masters[(day,exchange)]=idx
 master_results.append({'path':str(p.relative_to(ROOT)),'raw_digest_matches':digest(raw)==m.get('raw_sha256'),'manifest':m,'contracts_sha256':digest(contracts)})
summary=[]
for folder in sorted((ROOT/'quotes').iterdir()):
 day=folder.name
 groups={}
 for p in sorted(folder.iterdir()):
  if not (p.name.endswith('.gz') or p.name.endswith('.open')): continue
  files.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':digest(p)})
  opener=gzip.open if p.suffix=='.gz' else open
  with opener(p,'rt') as f:
   for line in f:
    e=json.loads(line);c=e.get('contract',{});name=c.get('underlying')
    if name not in ['NIFTY','SENSEX']:continue
    g=groups.setdefault(name,{'total':0,'option':0,'future':0,'valid':0,'reasons':collections.Counter(),'batches':collections.defaultdict(list),'tokens':collections.defaultdict(list),'ages':[],'raw_bad':0,'master_bad':0})
    g['total']+=1;received=ts(e['received_at_utc']);kind=c.get('instrument_type');g['option' if kind in ['CE','PE'] else 'future']+=1
    rawhash=hashlib.sha256(json.dumps(e['raw_packet'],sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    if rawhash!=e.get('raw_sha256'):g['raw_bad']+=1
    master=masters.get((day,c.get('exchange')),{}).get(str(c.get('instrument_token')))
    if master is None or any(str(master.get(k))!=str(c.get(k)) for k in ['tradingsymbol','expiry','instrument_type','lot_size']):g['master_bad']+=1
    g['tokens'][str(c['instrument_token'])].append(received)
    if kind not in ['CE','PE']: continue
    reason=None
    try:
     observed=ts(e['provider_timestamp_utc']);age=(received-observed).total_seconds();g['ages'].append(age)
     buy=e['buy_depth'][0];sell=e['sell_depth'][0];bid=float(buy['price']);ask=float(sell['price']);lot=int(c['lot_size'])
     if age<0:reason='future_provider_clock'
     elif age>30:reason='provider_age_over_30s'
     elif not (math.isfinite(bid) and math.isfinite(ask) and 0<bid<=ask):reason='invalid_top_book'
     elif min(buy['quantity'],sell['quantity'])<lot:reason='less_than_one_lot_top_depth'
     elif master is None:reason='master_missing'
    except (KeyError,TypeError,ValueError,IndexError): reason='missing_clock_or_book'
    if reason:g['reasons'][reason]+=1
    else:
     g['valid']+=1;g['batches'][received].append((c,bid,ask,observed))
 for name,g in groups.items():
  receipts=sorted(g['batches']); gaps=[(b-a).total_seconds() for a,b in zip(receipts,receipts[1:])]
  pairs=0;pair_batches=0;eligible_batches=0;deadline_batches=0;unique_pairs=set()
  for r,rows in g['batches'].items():
   found=0
   for i,(a,abid,aask,at) in enumerate(rows):
    for b,bbid,bask,bt in rows[i+1:]:
     if a['expiry']!=b['expiry'] or a['instrument_type']!=b['instrument_type'] or a['lot_size']!=b['lot_size'] or abs((at-bt).total_seconds())>5:continue
     low,high=((a,abid,aask),(b,bbid,bask)) if float(a['strike'])<float(b['strike']) else ((b,bbid,bask),(a,abid,aask))
     debit=low[2]-high[1] if a['instrument_type']=='CE' else high[2]-low[1]
     width=abs(float(a['strike'])-float(b['strike']))
     if 0<debit<width:
      found+=1;unique_pairs.add(tuple(sorted((a['instrument_token'],b['instrument_token']))))
   pairs+=found;pair_batches+=bool(found)
   local=r+timedelta(hours=5,minutes=30);minute=local.hour*60+local.minute
   eligible_batches+=bool(found and 560<=minute<=885)
   deadline_batches+=bool(found and minute==915)
  alltimes=[v for rows in g['tokens'].values() for v in rows]
  ages=sorted(g['ages'])
  summary.append({'day':day,'index':name,'packets':g['total'],'option_packets':g['option'],'future_packets':g['future'],'valid_one_lot_options_30s':g['valid'],'rejections':dict(g['reasons']),'raw_hash_mismatches':g['raw_bad'],'master_mismatches':g['master_bad'],'unique_tokens':len(g['tokens']),'first_receipt':min(alltimes).isoformat(),'last_receipt':max(alltimes).isoformat(),'usable_option_batches':len(receipts),'max_usable_batch_gap_seconds':max(gaps) if gaps else None,'gaps_over_90s':sum(x>90 for x in gaps),'provider_age_p95_seconds':ages[int(.95*(len(ages)-1))] if ages else None,'executable_vertical_pair_observations':pairs,'distinct_vertical_pairs':len(unique_pairs),'batches_with_pairs':pair_batches,'entry_window_batches_with_pairs':eligible_batches,'deadline_minute_batches_with_pairs':deadline_batches})
c=sqlite3.connect('file:/data/cache.db?mode=ro',uri=True)
db={}
for t in ['fno_signals','intraday_cache','partner_advisory_ideas','partner_advisory_research_artifacts','partner_advisory_strategy_qualifications']:
 db[t]={'columns':[r[1] for r in c.execute('pragma table_info('+t+')')],'rows':c.execute('select count(*) from '+t).fetchone()[0]}
db['fno_signal_days']=c.execute('select substr(evaluated_at,1,10),underlying,count(*),sum(accepted) from fno_signals group by 1,2 order by 1 desc limit 12').fetchall()
print(json.dumps({'assessed_at_utc':datetime.now(timezone.utc).isoformat(),'qualification':'INSUFFICIENT_EVIDENCE','scope':'data usability, not strategy expectancy or fills','files':files,'masters':master_results,'by_day_index':summary,'db':db},indent=2))
