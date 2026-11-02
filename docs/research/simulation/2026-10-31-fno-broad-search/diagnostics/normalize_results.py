"""Strict post-run result schema correction; preserve every original value."""
import copy,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]


def strict_bool(value):
    if type(value) is bool:return value
    if type(value) is str and value in ('True','False'):return value=='True'
    raise ValueError('ambiguous boolean check: '+repr(value))


def normalize(original,kind):
    result=copy.deepcopy(original);changed=0
    for name,c in result['candidates'].items():
        for key,value in c['checks'].items():
            new=strict_bool(value);changed+=type(value) is not bool;c['checks'][key]=new
        checks=c['checks']
        if kind=='screen':
            assert checks['max_t_p_le05']==(float(c['max_t_p'])<=.05)
            assert checks['t_ge2']==(float(c['weekly_t_unrounded'])>=2)
            assert c['invalid_replay'] is False
            assert c['screen_pass']==all(checks.values()),('screen verdict mismatch',name)
        else:
            assert checks['selected_max_t']==(float(c['selected_max_t_p'])<=.05)
            assert not result['correctness']['issues']
            assert c['passes']==all(checks.values()),('child verdict mismatch',name)
    result['schema']=original['schema']+'_strict_boolean_v2'
    result['reporting_correction']={'known_check_strings_converted':changed,'strategy_or_verdict_changed':False}
    return result,changed


def main():
    receipt={}
    for kind in ('screen','selected'):
        src=HERE/'calendar'/f'{kind}-results.json';dst=HERE/'calendar'/f'{kind}-results-v2.json'
        old=json.loads(src.read_text());new,count=normalize(old,kind)
        for name,candidate in old['candidates'].items():
            assert {k:v for k,v in candidate.items() if k!='checks'}=={k:v for k,v in new['candidates'][name].items() if k!='checks'},'non-check metric changed'
        dst.write_text(json.dumps(new,indent=2,allow_nan=False)+'\n')
        receipt[kind]={'original_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'normalized_sha256':hashlib.sha256(dst.read_bytes()).hexdigest(),'check_strings_converted':count,'verdicts_identical':True,'other_metrics_identical':True}
    (HERE/'result-schema-crosschecks.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('STRICT_RESULT_SCHEMA',receipt)


if __name__=='__main__':main()
