"""SN84: SN80 found the OPPOSITE of the web claim - a WIDE opening range (top third vs the last 20 sessions) predicts a
big day (34% of them reach a 1.3% range vs 8% for tight ones). The opening-range break on Gold-free days, only when the
opening range or CPR is wide. Same exits, NULL, stress and leave-one-year-out as SN81-83."""
import itertools, json, random, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn80 as Z
def gate_ok(r, gate):
    if r["adx"] is None or r["adx"] >= 30:
        return False
    ow = r["or_rank"] is not None and r["or_rank"] >= 0.67
    cw = r["cpr_rank"] is not None and r["cpr_rank"] >= 0.67
    return {"or_wide": ow, "cpr_wide": cw, "or_wide&cpr_wide": ow and cw, "or_wide|cpr_wide": ow or cw}[gate]
if __name__ == "__main__":
    T = Z.day_table()
    table, rng = {}, random.Random(84)
    for gate, buf, (en, ex), null in itertools.product(("or_wide", "cpr_wide", "or_wide&cpr_wide", "or_wide|cpr_wide"), (0.0, 0.25), Z.EXITS.items(), (False, True)):
        g = {"start": 30, "last_entry": 300, "max_trades": 1, "offset": 0, **ex}
        per = {}
        for y in Z.YEARS:
            nets = []
            for day, r in T.items():
                if r["year"] != y or not gate_ok(r, gate):
                    continue
                sig = Z.or_break_sig(r["S"], buf)
                if null and sig.any():
                    sig = sig * (1 if rng.random() < 0.5 else -1)
                nets.append(Z.Q.run_day(r["S"], g, 15000.0, 3000.0, 205.0, sig=sig)["net"])
            per[y] = {"net": round(sum(nets)), "green": sum(v > 0 for v in nets), "red": sum(v < 0 for v in nets), "none": sum(v == 0 for v in nets),
                      "refilled": round(sum(-v for v in nets if v < 0)), "days": len(nets)}
        table[f"{'NULL ' if null else ''}{gate} buf{buf} {en}"] = per
    for k, v in sorted(table.items(), key=lambda kv: -sum(x["net"] for x in kv[1].values()))[:8]:
        print(f"{k:42s}", [v[y]["net"] for y in Z.YEARS], sum(v[y]["net"] for y in Z.YEARS), "won/lost", sum(v[y]["green"] for y in Z.YEARS), sum(v[y]["red"] for y in Z.YEARS), "days", sum(v[y]["days"] for y in Z.YEARS))
    real = {k: v for k, v in table.items() if not k.startswith("NULL")}; nul = {k: v for k, v in table.items() if k.startswith("NULL")}
    Lr, Ln = Z.loyo(real, "profit"), Z.loyo(nul, "profit")
    print("LOYO real", {y: (Lr[y]["pick"], Lr[y]["net"]) for y in Z.YEARS}, "sum", Lr["sum"]["net"])
    print("LOYO null sum", Ln["sum"]["net"])
    (HERE / "results-sn84.json").write_text(json.dumps({"table": table, "loyo_real": Lr, "loyo_null": Ln}, indent=1, default=str), encoding="utf-8")
