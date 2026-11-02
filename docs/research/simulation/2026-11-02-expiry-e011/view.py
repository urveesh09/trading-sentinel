"""Print the frozen run's result."""
import json
from pathlib import Path

R = json.loads((Path(__file__).parent / "results.json").read_text())
print(json.dumps(R["decision"]))
seen = R["seen"]
for n in ("C", "E01", "STOP25", "RECOVER", "TRAIL3X", "E011", "E011R", "E011_S20", "E011_S30", "E011_K50", "E011R_S20", "E011R_S30", "E011R_K50", "E011_BOX35", "E011_BAND50"):
    o, a = seen[n]["ordinary"], seen[n]["adverse"]
    print(f"{n:13s} net {o['net']:9.2f} adv {a['net']:9.2f} worst {o['worst']:8.2f} advworst {a['worst']:8.2f} exbest {o['without_best']:8.2f} fall {o['drawdown']:8.2f} up/dn {o['up']}/{o['down']} ticket {o['ticket_net']:9.2f}")
print("per", seen["E011"]["ordinary"]["per"])
print("E01", seen["E01"]["ordinary"]["per"])
print("t2", json.dumps(R["t2"]))
print("t1", {k: v["passed"] for k, v in R["t1"].items()})
print("\nseptember")
for t in R["t5"]["tickets"]:
    print(t["day"], t["at"], t["kind"], t["rule"], "ask", t["ask"], {n: (t["arms"][n]["ordinary"], t["arms"][n]["adverse"]) for n in ("C", "E01", "STOP25", "RECOVER", "TRAIL3X", "E011", "E011R")})
    for n in ("E01", "E011", "E011R"):
        a = t["arms"][n]
        print("    ", n, "lots", a["lots"], "peak", a["peak"], a["status"], a["events"])
print(json.dumps(R["t5"]["total"]))
print("\nevery break, seen")
for name in ("E01", "E011", "E011R"):
    print(name, R["t4"]["summary"][name])
rows = {n: R["t4"]["tickets"][n] for n in ("E01", "E011", "E011R")}
for a, b, c in zip(rows["E01"], rows["E011"], rows["E011R"]):
    print(a["day"], a["at"], a["dir"], a["symbol"][-7:], "entry", a["entry"], "lots", a["lots"], "peak", c["peak"], "E01", a["net"], "E011", b["net"], "E011R", c["net"])
