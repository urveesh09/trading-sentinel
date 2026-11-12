"""SN03 round 2: stop new entries once the day is up, strike choice, combinations; then wallet growth caps 0..10."""
import json, time
import sn03 as Z
from sn03_run import loyo, show

if __name__ == "__main__":
    years = {y: Z.Year(y) for y in Z.YEARS}
    res = {}
    E = {"benchmark": {}}
    for dt in (1, 500, 1000, 1500, 3000):
        E[f"no new trade once day >= +{dt}"] = {"day_target": dt}
    for off in (-1, 1, 2):
        E[f"strike {'+' if off > 0 else ''}{off} from N11's"] = {"offset": off}
    E["drop SHIPPED + no new trade >= +1500"] = {"filter": {"kind": "expert_not", "value": ["SHIPPED"]}, "day_target": 1500}
    E["puts only + no new trade >= +1500"] = {"filter": {"kind": "side", "value": "PE"}, "day_target": 1500}
    E["drop SHIPPED + strike +1"] = {"filter": {"kind": "expert_not", "value": ["SHIPPED"]}, "offset": 1}
    E["puts only + strike +1"] = {"filter": {"kind": "side", "value": "PE"}, "offset": 1}
    E["2 lots when affordable"] = {"lots": 2}
    res["E"] = {k: {y: Z.year_result(years[y], v) for y in Z.YEARS} for k, v in E.items()}
    show("E", res["E"])
    for obj in ("profit", "calm"):
        L = loyo(res["E"], obj)
        print(f"LOYO E {obj:6s}", {y: (L[y]["pick"], L[y]["net"]) for y in Z.YEARS}, "sum", L["sum"], flush=True)
    res["caps"] = {}
    print("wallet growth (1 lot per Rs 15,000 of wallet), stop growing after step k:")
    for cap in list(range(0, 11)) + [99]:
        for s in (0.0, 205.0):
            r = Z.ledger(years, {"lots_follow": True}, cap=cap, stress=s)
            res["caps"][f"{cap}|{int(s)}"] = r
            if s == 205.0:
                print(f"  cap {cap:>2}: total {r['total']:>9} steps {r['steps']:>2} wallet {r['final_wallet']:>8} won/lost/none {r['green']}/{r['red']}/{r['none']} worst {r['worst']:>7} fall {r['fall']:>7} refilled {r['refilled']:>8}  last step {r['step_days'][-1] if r['step_days'] else '-'}", flush=True)
    Z.HERE.joinpath("_local", "round2.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
