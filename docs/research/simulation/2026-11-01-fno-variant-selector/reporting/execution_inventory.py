"""Read-only, privacy-minimal availability inventory; no broker/runtime imports."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


def inventory(data):
    db = sqlite3.connect(f'file:{data / "cache.db"}?mode=ro', uri=True)
    out = dict(schema='n06_execution_inventory_v1',observed_at_utc=datetime.now(timezone.utc).isoformat(),
               access='read-only mount; SQLite mode=ro; explicit read transaction; network none', tables={})
    try:
        db.execute('BEGIN')
        for table in ('fno_positions','fno_live_execution_events','fno_live_test_runs'):
            columns = [r[1] for r in db.execute(f'PRAGMA table_info({table})')]
            if not columns:
                out['tables'][table] = {'available':False}
                continue
            row = dict(available=True,rows=db.execute(f'SELECT count(*) FROM {table}').fetchone()[0])
            if table == 'fno_positions':
                row['counts_by_source_status'] = [dict(source=s,status=t,count=n) for s,t,n in db.execute('SELECT source,status,count(*) FROM fno_positions GROUP BY source,status')]
            elif table == 'fno_live_execution_events':
                row['counts_by_kind'] = {k:n for k,n in db.execute('SELECT kind,count(*) FROM fno_live_execution_events GROUP BY kind')}
                row['first_last_at'] = db.execute('SELECT min(at),max(at) FROM fno_live_execution_events').fetchone()
            out['tables'][table] = row
        out['quote_archive'] = dict(days=len(list((data/'research/quotes').glob('????-??-??'))),latest_day=max((p.name for p in (data/'research/quotes').glob('????-??-??')),default=None))
        out['exit_archive'] = dict(files=len(list((data/'research/fno_exit_paths').glob('*.jsonl'))),latest_day=max((p.stem for p in (data/'research/fno_exit_paths').glob('*.jsonl')),default=None))
    finally:
        db.close()
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result = inventory(a.data)
    if a.out.exists(): raise SystemExit('write-once inventory already exists')
    a.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
