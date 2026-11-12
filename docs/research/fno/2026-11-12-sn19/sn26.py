"""SN26 robustness (does the gain survive reality?) + SN29 last combination, every wallet.
SN26: SN Gold v2 / v3 at +Rs 300 and +Rs 400 per lot per trade instead of 205, and with every entry one minute late.
SN29: v3 with all lots every day in the growing wallet (no low-volatility halving)."""
import copy, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gold as Gd
G2 = {**Gd.GOLD, "itm_if_fits": True}
G3 = {**G2, "in_x": 0.10}
if __name__ == "__main__":
    vol = Gd.V.vol_days()
    years = {y: Gd.B.Year(y) for y in Gd.YEARS}
    out = {}
    for stress in (205.0, 300.0, 400.0):
        Gd.STRESS = stress
        for name, v in (("SN Gold", Gd.GOLD), ("SN Gold v2", G2), ("SN Gold v3", G3)):
            out[f"{name} +{int(stress)}"] = r = Gd.run(years, vol, v)
            print(Gd.line(f"{name} at +Rs {int(stress)}", r), flush=True)
    Gd.STRESS = 205.0
    # one minute late: shift every N11 entry by +1 minute (exits unchanged)
    for y, Y in years.items():
        late = {d: [{**s, "i": s["i"] + 1} for s in v] for d, v in Y.sigs("N11").items()}
        Y.streams["N11_ontime"] = Y.sigs("N11"); Y.streams["N11"] = late
    for name, v in (("SN Gold v2", G2), ("SN Gold v3", G3)):
        out[f"{name} 1 min late"] = r = Gd.run(years, vol, v)
        print(Gd.line(f"{name} entries 1 minute late", r), flush=True)
    for y, Y in years.items():
        Y.streams["N11"] = Y.streams["N11_ontime"]
    out["SN29 v3 all lots every day"] = r = Gd.run(years, vol, {**G3, "size": "all"})
    print(Gd.line("SN29 v3 all lots every day", r), flush=True)
    print("worst", {w: min(r[w][y]["worst"] for y in Gd.YEARS) for w in r})
    import json
    (HERE / "results-sn26-29.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
