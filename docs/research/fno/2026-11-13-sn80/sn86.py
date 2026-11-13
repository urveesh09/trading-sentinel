"""SN86-SN88 on Gold-free (ADX < 30) days: SN80's predicted big days (wide opening range) + the system's long-standing
put edge + the opening drive (O29b's one surviving filter). Baselines: random side at the same minute, and plain
puts bought at 09:45 on the same days. Exits HOLD (index trail) / QUICK, one lot, charges + Rs 205, LOYO."""
import itertools, json, random, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn80 as Z
def sig_for(S, kind, eff):
    F = S.F; c, o = F["c"], F["o"]
    n = len(c); sig = np.zeros(n, np.int8)
    rng_ = F["h"][:30].max() - F["l"][:30].min()
    drive = c[29] - o[0]
    if kind == "puts_break":
        s = Z.or_break_sig(S, 0.0); return np.where(s < 0, s, 0).astype(np.int8)
    if kind == "drive":
        if abs(drive) >= eff * rng_: sig[30] = 1 if drive > 0 else -1
        return sig
    if kind == "drive_puts":
        if drive <= -eff * rng_: sig[30] = -1
        return sig
    if kind == "plain_puts":
        sig[30] = -1; return sig
    raise ValueError(kind)
if __name__ == "__main__":
    T = Z.day_table(); rng = random.Random(86); table = {}
    for gate, (kind, eff), (en, ex), null in itertools.product(("gold_free", "gold_free&or_wide"),
            (("puts_break", 0), ("drive", 0.3), ("drive", 0.6), ("drive_puts", 0.3), ("drive_puts", 0.6), ("plain_puts", 0)),
            Z.EXITS.items(), (False, True)):
        if null and kind in ("plain_puts",):
            continue
        g = {"start": 30, "last_entry": 300, "max_trades": 1, "offset": 0, **ex}
        per = {}
        for y in Z.YEARS:
            nets = []
            for day, r in T.items():
                if r["year"] != y or r["adx"] is None or r["adx"] >= 30:
                    continue
                if gate.endswith("or_wide") and not (r["or_rank"] is not None and r["or_rank"] >= 0.67):
                    continue
                sig = sig_for(r["S"], kind, eff)
                if null and sig.any():
                    sig = sig * (1 if rng.random() < 0.5 else -1)
                nets.append(Z.Q.run_day(r["S"], g, 15000.0, 3000.0, 205.0, sig=sig)["net"])
            per[y] = {"net": round(sum(nets)), "green": sum(v > 0 for v in nets), "red": sum(v < 0 for v in nets), "none": sum(v == 0 for v in nets),
                      "refilled": round(sum(-v for v in nets if v < 0)), "days": len(nets)}
        table[f"{'NULL ' if null else ''}{gate} {kind}{eff} {en}"] = per
    for k, v in sorted(table.items(), key=lambda kv: -min(x["net"] for x in kv[1].values()))[:10]:
        print(f"{k:44s}", [v[y]["net"] for y in Z.YEARS], sum(v[y]["net"] for y in Z.YEARS), "won/lost", sum(v[y]["green"] for y in Z.YEARS), sum(v[y]["red"] for y in Z.YEARS))
    real = {k: v for k, v in table.items() if not k.startswith("NULL")}; nul = {k: v for k, v in table.items() if k.startswith("NULL")}
    Lr, Ln = Z.loyo(real, "profit"), Z.loyo(nul, "profit")
    print("LOYO real", {y: (Lr[y]["pick"], Lr[y]["net"]) for y in Z.YEARS}, "sum", Lr["sum"]["net"]); print("LOYO null sum", Ln["sum"]["net"])
    print("all-years-positive real:", [k for k, v in real.items() if all(v[y]["net"] > 0 for y in Z.YEARS)])
    (HERE / "results-sn86.json").write_text(json.dumps({"table": table, "loyo_real": Lr, "loyo_null": Ln}, indent=1, default=str), encoding="utf-8")
