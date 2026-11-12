"""Wallet stopped after step k (0..5), per strategy, Jan 2023 - Oct 2026, +Rs 205 per lot per trade (descriptive)."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "2026-11-12-sn03")]
import sn03 as Z
STRATS = {
    "A. Benchmark (N11 entries + exits)": {},
    "B. A without SHIPPED trades": {"filter": {"kind": "expert_not", "value": ["SHIPPED"]}},
    "C. A, puts only": {"filter": {"kind": "side", "value": "PE"}},
    "D. A + owner's 10%: no new trade once day >= +10% of wallet": {"day_target_share": 0.10},
}
if __name__ == "__main__":
    years = {y: Z.Year(y) for y in Z.YEARS}
    out = {}
    for name, v in STRATS.items():
        for cap in range(0, 6):
            vv = {k: x for k, x in v.items() if k != "day_target_share"}
            if "day_target_share" in v:
                vv["day_target"] = 1500.0   # 10% of the starting wallet (the owner's minimum target)
            r = Z.ledger(years, {**vv, "lots_follow": True}, cap=cap)
            out[f"{name}|{cap}"] = r
            print(f"{name[:2]} cap {cap}: profit {r['total']:>8}  won/lost/none {r['green']}/{r['red']}/{r['none']}  refilled {r['refilled']:>7}  won-days total {r['total']+r['refilled']:>8}  worst {r['worst']:>7}  fall {r['fall']:>6}  wallet {r['final_wallet']}", flush=True)
    (HERE / "results-caps.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
