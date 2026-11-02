import copy,json,sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import normalize_results as N


def sample():
    return {'schema':'test','correctness':{'issues':{}},'candidates':{'one':{'checks':{'selected_max_t':np.float64(.9)<=.05,'other':True},'passes':False,'selected_max_t_p':.9,'net':123.4}}}


def test_real_numpy_json_default_string_reproducer_and_unchanged_economics():
    before=json.loads(json.dumps(sample(),default=str))
    assert before['candidates']['one']['checks']['selected_max_t']=='False'
    assert bool(before['candidates']['one']['checks']['selected_max_t']) is True
    fixed,count=N.normalize(before,'selected')
    assert count==1 and fixed['candidates']['one']['checks']['selected_max_t'] is False
    assert fixed['candidates']['one']['net']==123.4 and fixed['candidates']['one']['passes'] is False
    assert before['candidates']['one']['checks']['selected_max_t']=='False','original must stay intact'


@pytest.mark.parametrize('value',['false','TRUE','0',0,1,None,[],{}])
def test_ambiguous_flags_refused(value):
    with pytest.raises(ValueError):N.strict_bool(value)


def test_inconsistent_numeric_check_or_verdict_refused():
    x=json.loads(json.dumps(sample(),default=str));x['candidates']['one']['checks']['selected_max_t']='True'
    with pytest.raises(AssertionError):N.normalize(x,'selected')
    x=json.loads(json.dumps(sample(),default=str));x['candidates']['one']['passes']=True
    with pytest.raises(AssertionError):N.normalize(x,'selected')


def test_correct_boolean_idempotent():
    x=json.loads(json.dumps(sample(),default=str));a,_=N.normalize(x,'selected');b,count=N.normalize(a,'selected')
    assert count==0 and a['candidates']==b['candidates']
