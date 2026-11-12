"""SN07: play each relaxed N11 book's trades in the Rs 15,000 wallet (one lot, OTM substitute, +Rs 205)."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "2026-11-12-sn03")]
import sn03 as B
E = ("entry_time", "tradingsymbol", "entry_premium", "exit_time", "exit_premium", "exit_reason", "net_pnl", "entry_qty")
out = {}
for y in B.YEARS:
    keys = json.loads((HERE / f"_local/keys-{y}.json").read_text())
    Y = B.Year(y)
    stored = json.loads((B.N11 / f"_local/evals/{keys['N11']}.json").read_text())["trades"]
    mine = json.loads((HERE / f"_local/evals/{keys['N11']}.json").read_text())["trades"]
    parity = [tuple(t[e] for e in E) for t in mine] == [tuple(t[e] for e in E) for t in stored]
    for name, k in keys.items():
        T = json.loads((HERE / f"_local/evals/{k}.json").read_text())["trades"]
        by = {}
        for t in T:
            ctx = t["n091_entry"]["native_gate_context"]; sym = t["tradingsymbol"]
            s = {"day": t["entry_time"][:10], "i": B.minute_of(t["entry_time"]), "j": B.minute_of(t["exit_time"]),
                 "strike": int(round(ctx["strike"])), "opt": "CE" if ctx["is_call"] else "PE",
                 "expiry": f"20{sym[5:7]}-{sym[7:9]}-{sym[9:11]}", "reason": t["exit_reason"], "expert": t["entry_expert"],
                 "gate": "", "book": name, "sig_key": (t["entry_time"][:16], int(round(ctx["strike"])), ctx["is_call"])}
            by.setdefault(s["day"], []).append(s)
        Y.streams[name] = by
        r = B.year_result(Y, {}, books=(name,))
        out.setdefault(name, {})[y] = {**r, "engine_trades": len(T), "parity": parity}
for name, per in out.items():
    print(name, {y: (per[y]["net"], per[y]["green"], per[y]["red"], per[y]["none"]) for y in B.YEARS},
          "total", sum(per[y]["net"] for y in B.YEARS), "refill", sum(per[y]["refilled"] for y in B.YEARS),
          "engine trades", sum(per[y]["engine_trades"] for y in B.YEARS), "parity", all(per[y]["parity"] for y in B.YEARS))
(HERE / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
