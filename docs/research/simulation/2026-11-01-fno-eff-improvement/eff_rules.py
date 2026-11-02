"""Two fixed EFF hypotheses. No broker, capital, scheduler or prediction model."""
import copy
from datetime import datetime

class RetestState:
    def __init__(self):self.pending=None;self.cache_key=None;self.cached=(None,{})
    def step(self,original,ctx,regime):
        if not ctx or not ctx['fresh'] or regime=='REGIME_3_CRISIS':
            self.pending=None;self.cache_key=None;return None,{'reason':'unavailable_or_crisis'}
        key=(ctx['bar'],regime)
        if key==self.cache_key:return copy.copy(self.cached[0]),copy.deepcopy(self.cached[1])
        now=datetime.fromisoformat(ctx['bar']);p=self.pending;answer=None;info={'reason':'waiting'}
        if p:
            age=(now-datetime.fromisoformat(p['bar'])).total_seconds()/60;sign=p['sign'];zone=.25*p['atr']
            valid=now.date().isoformat()==p['bar'][:10] and 0<age<=15 and age%5==0 and ctx['consecutive_from']<=p['bar']
            valid=valid and sign*(ctx['close']-p['level'])>=-zone and (ctx['low']>p['signal'].stop_underlying if sign==1 else ctx['high']<p['signal'].stop_underlying)
            if not valid:self.pending=None
            elif ctx['low']<=p['level']+zone and ctx['high']>=p['level']-zone and sign*(ctx['close']-p['level'])>0 and sign*(ctx['close']-ctx['open'])>0 and sign*(ctx['close']-ctx['previous_close'])>0:
                answer=copy.copy(p['signal']);answer.bar_ts=ctx['bar'];answer.close=ctx['close'];answer.atr=ctx['atr'];answer.rvol=ctx['rvol']
                risk=sign*(ctx['close']-answer.stop_underlying);answer.target_underlying=ctx['close']+sign*1.8*risk
                info={'reason':'retest_confirmed','source_bar':p['bar'],'confirmation_bar':ctx['bar'],'broken_level':p['level'],'zone_atr':p['atr'],'original_stop':answer.stop_underlying}
                self.pending=None
        if answer is None and original.direction is not None:
            sign=1 if original.direction.value=='LONG' else -1
            if self.pending is None or self.pending['sign']!=sign:
                self.pending={'signal':copy.copy(original),'bar':ctx['bar'],'sign':sign,'level':ctx['prior4high'] if sign==1 else ctx['prior4low'],'atr':original.atr}
                info={'reason':'armed','source_bar':ctx['bar']}
        self.cache_key=key;self.cached=(copy.copy(answer),copy.deepcopy(info));return answer,info

def horizon(age,trail,net,progress,ctx,direction):
    """Soft clock only; the ordinary exit evaluator keeps all urgent exits."""
    if 30<=age<60 and not trail and net is not None and net<=0 and progress<.5:return 30.,'STALL30'
    sign=1 if direction=='LONG' else -1
    continued=bool(ctx and ctx['fresh'] and ctx['valid_volume'] and sign*(ctx['close']-ctx['vwap'])>0 and sign*(ctx['close']-ctx['previous_close'])>0)
    if 60<=age<90 and net is not None and net>0 and progress>=1 and continued:return 90.,'CONTINUE90'
    return 60.,'BASE60'
