"""Frozen-rule sanity check on the same five already-seen 2026 recordings.

This reuses E03's sampled-bar adapter, NOT raw native-depth execution. No new
forward paper tickets and no full-2026-chain coverage can be claimed from it.
"""
import socket
def denied(*args,**kwargs):raise AssertionError('Network forbidden in recorded proxy')
socket.socket.connect=denied;socket.create_connection=denied
import json
import lab as L
import study as S
import native as N

def main():
    rule=L.Candidate(**json.loads((L.HERE/'finalists-freeze.json').read_text())['finalists']['DEFENSIVE'])
    S.freeze('recorded-proxy-freeze.json',dict(status='Five dates already inspected by E03; NOT fresh E031 forward evidence',
       source={str(p):L.D.sha(p) for p in (N.EXPORT,N.EXTRA) if p.exists()},adapter_sha256=L.D.sha(N.__file__),rule=rule.__dict__))
    ts=N.tapes();out={}
    for name,r in (('E03',L.BASE),('E031',rule)):
        out[name]={}
        for sc in ('ordinary','adverse'):
            result=L.run(ts,r,sc,True)
            out[name][sc]=result
            print('RECORDED_PROXY',name,sc,result['summary']['net'],result['summary']['trades'],flush=True)
    S.save('recorded-proxy.json',dict(dates=[t.day for t in ts],results=out,
       classification='ALREADY_SEEN_RECORDED_QUOTE_TO_BAR_PROXY; not native live execution, not new forward qualification',
       limitations=['Inherited adapter approximates mid OHLC and depth as volume','Older compact quotes and sample gaps are lower fidelity',
                    'No point-in-time complete master/universe evidence or full-year option chain','E031 was disabled, so these were not live shadow tickets']))

if __name__=='__main__':main()
