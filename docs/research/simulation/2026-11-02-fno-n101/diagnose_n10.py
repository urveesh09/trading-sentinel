"""Post-freeze diagnosis of the inherited underlying-lock assumption; no candidate tuning."""
import json
from pathlib import Path

from audit_n101 import fees, net

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/"2026-11-01-fno-n10"/"_local"


def main():
    rows=[]
    for year in ("2023","2024","2025","2026"):
        key=json.loads((OLD/f"keys-panel2-{year}.json").read_text())["R2_THIRD_CW"]
        for t in json.loads((OLD/"evals"/f"{key}.json").read_text())["trades"]:
            for c in t.get("n10_children") or []:
                parent_at_original_stop=net(t["entry_premium"],round(.75*t["entry_premium"],2),t["entry_qty"],420)
                child_at_stop=net(c["ask"],c["premium_stop"],c["qty"],205)
                rows.append({"year":year,"entry_at":t["entry_time"],"add_at":c["at"],"symbol":t["tradingsymbol"],
                             "n10_planned_total":c["planned_total"],"child_planned_risk":c["risk"],
                             "child_actual_premium_stop_loss":-child_at_stop,"combined_original_premium_stop_loss":-parent_at_original_stop-child_at_stop,
                             "realized_child_net":c["net"],"realized_trade_net":t["net_pnl"]})
    out={"child_lots":len(rows),"child_cost_aware_stop_loss_above_declared_risk":sum(r["child_actual_premium_stop_loss"]>r["child_planned_risk"]+.01 for r in rows),
         "original_combined_backstop_exposure_above_5000":sum(r["combined_original_premium_stop_loss"]>5000 for r in rows),"rows":rows,
         "meaning":"Diagnostic of planned risk assumptions, not additional realized losses: an underlying stop can exit sooner, but does not guarantee an option price. N10 arithmetic/P&L is unchanged."}
    (HERE/"n10-risk-diagnosis.json").write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in out.items() if k!="rows"}))


if __name__=="__main__":
    main()
