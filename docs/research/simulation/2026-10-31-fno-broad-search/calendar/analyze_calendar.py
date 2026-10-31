"""Reuse unchanged parent judgments against explicit corrected/reused receipts."""
import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parent)]
import calendar_lab as C
import analyze_broad as A


def arrays(phase):
    f=A.load(C.PARENT/'freeze.json');keys={};cache={};issues={};reuse={}
    sessions={y:[d for d in A.load(C.B.ROOT/f['bindings'][y]['dataset']/'manifest.json')['sessions'] if d<=A.A.A.LAST[y]] for y in A.YEARS}
    for y in A.YEARS:
        base=HERE if phase=='selected' or y=='2024' else C.PARENT
        keys[y]=A.load(base/f'_local/keys-{phase}-{y}.json')
        for name,key in keys[y].items():
            file=base/'_local/evals'/f'{key}.json';obj=A.load(file);rows=obj['trades'];book=obj['book']
            cache.setdefault(name,{})[y]=rows
            bad=A.FIN.check_book(rows,{'cfg':book['cfg']},A.FIN.CAPITAL,book.get('cost'),book['cfg'].get('FNO_MAX_TRADES_PER_DAY',3))
            notes={k:v for k,v in obj['notes'].items() if 'conflict' in k or k=='named_memo_miss'}
            if bad or notes:issues[f'{y}|{name}']={'financial':bad,'memo':notes}
            if base==C.PARENT:
                assert all(d not in C.SPECIAL for d in sessions[y]),'reuse crossed corrected calendar'
                reuse[f'{y}|{name}']={'file':file.relative_to(C.B.ROOT).as_posix(),'sha256':C.B.P.sha(file),'clock_override_active':False}
    C.B.P.write(HERE/f'_local/reuse-{phase}.json',reuse)
    return f,keys,sessions,cache,issues


if __name__=='__main__':
    A.HERE=HERE
    A.arrays=arrays
    {'screen':A.screen,'selected':A.selected}[sys.argv[1]]()
