"""OAR development rounds on seen daily panels (scripts/rounds.py 1|2|3...)."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import oarsim as o  # noqa: E402

P = o.Policy
ROUNDS = {
    1: [P("OAR_GAP"), P("OAR_VAL", rank="value"), P("OAR_HIST", rank="hist"),
        P("OAR_RANDOM", rank="random", extra=("r1",)), P("OAR_GAP3", gap_max=-0.03),
        P("OAR_MID", gap_min=-0.10), P("OAR_GAP_1", slots=1), P("OAR_GAP_3", slots=3),
        P("OAR_NIGHT", exit="next_open")],
    2: [P("OAR_CAP", cap_filter=0.001), P("OAR_CAP4", slots=4, cap_filter=0.001), P("OAR_NOBAND", skip_band=True),
        P("OAR_CAP_NOBAND", cap_filter=0.001, skip_band=True), P("OAR_HIST_CAP", rank="hist", cap_filter=0.001),
        P("OAR_CAP_HISTOK", cap_filter=0.001, hist_ok=True)],
    "2s": [P("S1", slots=1), P("S2", slots=2), P("S1_CAP", slots=1, cap_filter=0.001), P("S2_CAP", slots=2, cap_filter=0.001)],
}


def run(n, bankroll=25000.0):
    pan = o.panels()["rows"]
    out = {}
    for p in ROUNDS[n]:
        out[p.name] = {}
        for name, (s, e) in o.PANELS.items():
            out[p.name][name] = o.score(pan[name], p, s, e, bankroll=bankroll)
        r = out[p.name]
        print(f"{p.name:12s} M1 " + " ".join(f"{r[k]['M1']['net']:>10,.0f}" for k in o.PANELS)
              + " | robust " + " ".join(f"{r[k]['robust']:>9,.0f}" for k in o.PANELS)
              + " | M3 " + " ".join(f"{r[k]['M3']['net']:>9,.0f}" for k in o.PANELS), flush=True)
    (HERE / f"results/round{n}{'' if bankroll == 25000 else '-' + str(int(bankroll))}.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    k = sys.argv[1]
    run(int(k) if k.isdigit() else k, float(sys.argv[2]) if len(sys.argv) > 2 else 25000.0)
