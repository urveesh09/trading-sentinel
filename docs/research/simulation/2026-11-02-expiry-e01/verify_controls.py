"""Historical schema-aware parity, preserving original failed strict comparisons."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def normalize_absent_schema(mismatch):
    # bank_pending did not exist in Oct6's table. Later migration adds DEFAULT0.
    return mismatch["field"]=="bank_pending" and mismatch["replay"] is None and mismatch["observed"]==0


def main():
    paths=sorted((HERE/"_local/evals").glob("*-HISTORY-v3-ordinary.json"));assert len(paths)==8
    out=[]
    for path in paths:
        case=json.loads(path.read_text());bad=case["historical_parity"]["mismatches"]
        actual=[m for m in bad if not (case["day"]=="2026-10-06" and normalize_absent_schema(m))]
        out.append(dict(day=case["day"],underlying=case["underlying"],positions=case["historical_parity"]["observed_positions"],
                        exact_money_events=True if not actual else False,legacy_schema_defaults=len(bad)-len(actual),mismatches=actual))
    result=dict(passed=not any(r["mismatches"] for r in out),cases=out,
                note="Oct6 raw index clocks unavailable, observed values used; five later DEFAULT0 bank_pending columns normalized only in comparison. No money, quote or event normalized.")
    (HERE/"control-parity.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    assert result["passed"],out
    print("HISTORICAL_PARITY",len(out),sum(r["positions"] for r in out),"positions")


if __name__=="__main__":main()
