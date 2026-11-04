"""Bounded research-only Penny data/search driver; no broker or runtime mutation."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-engine"))


def atomic(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temp.replace(path)


def acquire(run):
    from backtest_all_yahoo import fetch_chart, chunks
    names = json.loads((run / "universe.json").read_text())["symbols"]
    local = run / "_local" / "public"
    local.mkdir(parents=True, exist_ok=True)
    jobs = [(s, "1m", a, b) for s in names for a, b in chunks("2026-10-07", "2026-11-03", "1m")]
    jobs += [(s, "1d", "2019-01-01", "2026-11-03") for s in [*names, "NIFTYBEES"]]
    target = local / "public.sqlite"
    if target.exists():
        raise ValueError("acquisition output already exists; evidence is immutable")
    con = sqlite3.connect(target)
    con.execute("CREATE TABLE intraday_cache(ticker TEXT,interval TEXT,datetime TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,PRIMARY KEY(ticker,interval,datetime))")
    con.execute("CREATE TABLE ohlcv_cache(ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,PRIMARY KEY(ticker,date))")
    receipts = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = {pool.submit(fetch_chart, local, s, s + ".NS", i, a, b): (s, i, a, b) for s, i, a, b in jobs}
        for future in as_completed(pending):
            identity = pending[future]
            try:
                rows, receipt = future.result()
                table = "ohlcv_cache" if identity[1] == "1d" else "intraday_cache"
                count = 7 if table == "ohlcv_cache" else 8
                con.executemany(f"INSERT OR IGNORE INTO {table} VALUES ({','.join('?' * count)})", rows)
                con.commit()
                receipts.append(receipt)
            except Exception as exc:
                receipts.append({"job": identity, "state": "FAILED", "reason": repr(exc)})
            if len(receipts) % 25 == 0:
                atomic(local / "acquisition-progress.json", receipts)
                print(f"acquired {len(receipts)}/{len(jobs)}", flush=True)
    con.close()
    atomic(run / "public-acquisition.json", {"as_of": datetime.now(timezone.utc).isoformat(), "breeze_calls": 0, "broker_calls": 0, "receipts": receipts})
    print("acquisition complete", flush=True)


def prepare(run):
    """New immutable source-priority snapshot; count conflicts, never edit inputs."""
    from research_data_contracts import load_daily_dataset, load_intraday_dataset
    target=run/'_local'/'research.sqlite'
    if target.exists(): raise ValueError('snapshot exists')
    con=sqlite3.connect(target)
    con.execute('CREATE TABLE ohlcv_cache(ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,PRIMARY KEY(ticker,date))')
    con.execute('CREATE TABLE intraday_cache(ticker TEXT,interval TEXT,datetime TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,PRIMARY KEY(ticker,interval,datetime))')
    public=run/'_local'/'public'/'public.sqlite'
    p=sqlite3.connect(public.as_uri()+'?mode=ro',uri=True)
    con.executemany('INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)',p.execute('SELECT * FROM ohlcv_cache'))
    p.close()
    sources=[(ROOT/'docs/research/yahoo/2026-10-04-penny-trader-window/_local/validated-yahoo.sqlite','2026-09-07','2026-10-01'),
             (run/'_local'/'production-cash.sqlite','2026-10-02','2026-10-06'),
             (public,'2026-10-07','2026-11-03')]
    provenance=[]
    for path,start,end in sources:
        c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
        cursor=c.execute("SELECT ticker,interval,datetime,open,high,low,close,volume FROM intraday_cache WHERE interval='minute' AND substr(datetime,1,10) BETWEEN ? AND ?",(start,end))
        count=0
        while True:
            rows=cursor.fetchmany(10000)
            if not rows: break
            con.executemany('INSERT INTO intraday_cache VALUES (?,?,?,?,?,?,?,?)',rows);count+=len(rows)
        c.close();provenance.append({'path':str(path),'start':start,'end':end,'rows':count})
    con.commit();con.close()
    names=json.loads((run/'universe.json').read_text())['symbols']
    daily=load_daily_dataset(target,tickers=[*names,'NIFTYBEES'],before='2026-11-04')
    intra=load_intraday_dataset(target,interval='minute',start='2026-09-07',end='2026-11-03',tickers=names)
    by_window={}
    for window,start,end in [('development','2026-09-07','2026-10-16'),('validation','2026-10-19','2026-11-03')]:
        from collections import Counter
        rows=[r for r in intra.coverage if start<=r['trading_date']<=end]
        by_window[window]={'status_counts':dict(Counter(r['status'] for r in rows)),
                          'symbols_with_bars':len({t for (t,d) in intra.bars if start<=d<=end})}
    atomic(run/'coverage.json',{'daily':daily.manifest,'daily_invalid':daily.invalid,
                               'intraday':intra.manifest,'windows':by_window,'sources':provenance,
                               'no_strategy_results_inspected':True,
                               'snapshot_sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    print(json.dumps(by_window),flush=True)


def load_inputs(run, start, end, *, intraday=True):
    from research_data_contracts import load_daily_dataset, load_intraday_dataset
    names=json.loads((run/'universe.json').read_text())['symbols']
    path=run/'_local'/'research.sqlite'
    # Nov 3's provider daily close is incomplete. No entry through Nov 3 needs
    # that final daily candle: prior-day-only warmup ends Nov 2. Earlier windows
    # similarly never read future daily data for a validity decision.
    cutoff=min(end,'2026-11-03')
    daily=load_daily_dataset(path,tickers=[*names,'NIFTYBEES'],before=cutoff)
    if not intraday: return names,daily,None
    tape=load_intraday_dataset(path,interval='minute',start=start,end=end,tickers=names)
    return names,daily,tape


def freeze(run):
    from collections import Counter
    names,daily,tape=load_inputs(run,'2026-09-07','2026-11-03')
    # The compute bound is based solely on development observation availability.
    # Validation cannot change which symbols the intraday experiment requests.
    counts=Counter({t:sum(len(b) for (s,d),b in tape.bars.items() if s==t and d<='2026-10-16')
                    for t in names if t not in daily.invalid})
    chosen=sorted(counts,key=lambda t:(-counts[t],t))[:24]
    source={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [*sorted((ROOT/'python-engine').glob('*.py')),Path(__file__).resolve()]}
    manifest={'schema':'penny_strategy_search_freeze_v1','source':source,
              'snapshot_sha256':hashlib.sha256((run/'_local/research.sqlite').read_bytes()).hexdigest(),
              'intraday_symbols':chosen,'all_symbols':names,'selection_rule':'top24 development available native minute rows; ties alphabetical; no outcomes',
              'intraday_training':['2026-09-07','2026-10-16'],
              'intraday_validation':['2026-10-19','2026-11-03'],
              'daily_training':['2019-01-01','2022-12-30'],
              'daily_calibration':['2023-01-01','2023-12-29'],
              'daily_validation':['2024-01-01','2025-12-31'],
              'validation_status':'conditional historical validation: related dates previously used by Sentinel; not untouched qualification',
              'intraday_bankroll':2000,'daily_bankroll':100000,'daily_secondary_bankroll':2000,
              'round_limit':3,'new_candidates_per_family_per_round':2,
              'genome_trials_max':12,'genome_seed':20261104,
              'acceptance':'positive net, positive ex-best, beats baseline, DD <= max(1.5x baseline, 2.5% bankroll), >=20 closes, no unresolved; identical costs/cash',
              'stress':'intraday 10/30/60 bps total spread; daily 10/30/60 bps per side',
              'reserved_jan_jul_exam':'not opened or scored',
              'daily_invalid_without_unused_Nov3_close':daily.invalid}
    path=run/'freeze.json'
    if path.exists():raise ValueError('freeze already exists')
    atomic(path,manifest)
    print('freeze written',len(chosen),'intraday symbols; daily invalid',len(daily.invalid),flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["acquire","prepare","freeze"])
    p.add_argument("--run", type=Path, required=True)
    a = p.parse_args()
    {'acquire':acquire,'prepare':prepare,'freeze':freeze}[a.command](a.run.resolve())


if __name__ == "__main__":
    main()
