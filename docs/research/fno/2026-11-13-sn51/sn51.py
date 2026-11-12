"""SN51 - SN Gold v4 (frozen harness, read only) with the owner's questions: start Rs 15k / 20k / 30k, growth stopped
after 3 / 5 / never (no size cap), steps after 100% or 50% of the wallet in profit. Net at the end = won - refilled."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "sn-gold"))
import gold_v4 as G
cfg = json.loads((HERE.parent / "sn-gold" / "SN_GOLD_V4.json").read_text(encoding="utf-8"))
V4 = {**cfg["variant_dict"], "itm_auto": tuple(cfg["variant_dict"]["itm_auto"])}
if __name__ == "__main__":
    G.VOLT.update(G.vol_table())
    years = {y: G.B.Year(y) for y in G.YEARS}
    rows = {}
    for W0 in (15000.0, 20000.0, 30000.0):
        for trig in (1.0, 0.5):
            G.WALLETS = tuple((f"start {int(W0/1000)}k, step after {int(trig*100)}%, stop after {cap}", W0, "grow", cap) for cap in (3, 5, 99))
            r = G.run(years, None, {**V4, "g_trig": trig})
            for w, per in r.items():
                won = sum(per[y]["net"] + per[y]["refilled"] for y in G.YEARS); ref = sum(per[y]["refilled"] for y in G.YEARS)
                rows[w] = {"won_on_green_days": won, "refilled": ref, "net_at_end": won - ref, "worst": min(per[y]["worst"] for y in G.YEARS),
                           "per_year_net": {y: per[y]["net"] for y in G.YEARS}}
                print(f"{w.replace('stop after 99', 'no size cap'):42s} won {won:>9} refilled {ref:>9} NET {won-ref:>9} worst {rows[w]['worst']:>8}  by year {[per[y]['net'] for y in G.YEARS]}", flush=True)
    (HERE / "results-sn51.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
