"""SN08: each relaxed N11 book in the Rs 15,000 wallet, per year; leave one year out among them + the benchmark."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "2026-11-12-sn03"), str(HERE.parent / "2026-11-12-sn03")]
import sn03 as B
from sn03_run import loyo
def stream(T, name):
    by = {}
    for t in T:
        ctx = t["n091_entry"]["native_gate_context"]; sym = t["tradingsymbol"]
        s = {"day": t["entry_time"][:10], "i": B.minute_of(t["entry_time"]), "j": B.minute_of(t["exit_time"]),
             "strike": int(round(ctx["strike"])), "opt": "CE" if ctx["is_call"] else "PE",
             "expiry": f"20{sym[5:7]}-{sym[7:9]}-{sym[9:11]}", "reason": t["exit_reason"], "expert": t["entry_expert"],
             "gate": t.get("entry_gate") or "", "book": name, "sig_key": (t["entry_time"][:16], int(round(ctx["strike"])), ctx["is_call"])}
        by.setdefault(s["day"], []).append(s)
    return by
table = {}
for y in B.YEARS:
    Y = B.Year(y)
    table.setdefault("N11 (benchmark)", {})[y] = B.year_result(Y, {})
    keys = json.loads((HERE / f"_local/keys-{y}.json").read_text())
    for name, k in keys.items():
        T = json.loads((HERE / f"_local/evals/{k}.json").read_text())["trades"]
        Y.streams[name] = stream(T, name)
        r = B.year_result(Y, {}, books=(name,)); r["engine_trades"] = len(T)
        table.setdefault(name, {})[y] = r
for n, per in table.items():
    print(f"{n:16s}", " ".join(f"{per[y]['net']:>7}" for y in B.YEARS), f"= {sum(per[y]['net'] for y in B.YEARS):>8}",
          "won/lost/none", sum(per[y]["green"] for y in B.YEARS), sum(per[y]["red"] for y in B.YEARS), sum(per[y]["none"] for y in B.YEARS),
          "refill", sum(per[y]["refilled"] for y in B.YEARS))
L = loyo(table, "profit")
print("LOYO", {y: (L[y]["pick"], L[y]["net"]) for y in B.YEARS}, "sum", L["sum"])
(HERE / "results.json").write_text(json.dumps({"table": table, "loyo": L}, indent=1), encoding="utf-8")
