"""Win/loss anatomy of every EN arm and of E03.2 itself (owner's rule, Nov 17): where each arm won and lost and
how much, and what it added, removed or changed against E03.2. It replays the same frozen arms with the same
labs and coverage rule. Each total is asserted against the scored results (results.json, results2.json,
exam2023b-results.json), so nothing here is a new score and nothing is re-tuned. -> anatomy.json, ANATOMY.md
"""
from __future__ import annotations
import json
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
import numpy as np
import en_lab2 as M
import exam2023b as C

HERE = Path(__file__).resolve().parent
E = M.E
R1 = json.loads((HERE / "results.json").read_text()); R2 = json.loads((HERE / "results2.json").read_text())
RX = json.loads((HERE / "exam2023b-results.json").read_text())
ARMS = {
    "E03.2 (control)": ({}, (2023, 2024, 2025)),
    "EN03 put gate 0.65": (dict(put_eff=.65), (2024, 2025)), "EN03 put gate 0.60": (dict(put_eff=.60), (2024, 2025)),
    "EN03 put gate 0.55": (dict(put_eff=.55), (2024, 2025)),
    "EN04 puts 2.5x": (dict(put_mult=2.5), (2023, 2024, 2025)), "EN04 puts 3x": (dict(put_mult=3.), (2023, 2024, 2025)),
    "EN04 puts 3.5x": (dict(put_mult=3.5), (2023, 2024, 2025)),
    "EN05 put runner 1.2": (dict(put_runner=1.2), (2024, 2025)),
    "EN08 calm-morning gate": (dict(regime_min=R2["EN08"]["thresholds"]["calm_below"]), (2023, 2024, 2025)),
    "EN09 breakout added": (dict(squeeze="add"), (2023, 2024, 2025)), "EN09 breakout alone": (dict(squeeze="only"), (2023, 2024, 2025)),
    "EN10 one-lot bank": (dict(bank_r=1.), (2023, 2024, 2025)),
}
SAVED = {  # (arm, year) -> scored ordinary net, for the parity assertion
    **{("E03.2 (control)", y): R2["E032"][f"{y}|ordinary"]["net"] for y in (2023, 2024, 2025)},
    **{(f"EN03 put gate {v}", y): R1["arms"][f"EN03_eff{v}"][f"{y}|ordinary"]["net"] for v in ("0.65", "0.60", "0.55") for y in (2024, 2025)},
    **{(f"EN04 puts {v}x", y): R1["arms"][f"EN04_put{v}x"][f"{y}|ordinary"]["net"] for v in ("2.5", "3", "3.5") for y in (2024, 2025)},
    **{(f"EN04 puts {v}x", 2023): RX["arms"][f"EN04_put{v}x"]["ordinary"]["net"] for v in ("2.5", "3", "3.5")},
    **{("EN05 put runner 1.2", y): R1["arms"]["EN05_run1.2"][f"{y}|ordinary"]["net"] for y in (2024, 2025)},
    **{("EN08 calm-morning gate", y): R2["EN08"]["arm"][f"{y}|ordinary"]["net"] for y in (2023, 2024, 2025)},
    **{("EN09 breakout added", y): R2["EN09"]["add"][f"{y}|ordinary"]["net"] for y in (2023, 2024, 2025)},
    **{("EN09 breakout alone", y): R2["EN09"]["only"][f"{y}|ordinary"]["net"] for y in (2023, 2024, 2025)},
    **{("EN10 one-lot bank", y): R2["EN10"]["arm"][f"{y}|ordinary"]["net"] for y in (2023, 2024, 2025)},
}


def hhmm(m):return f"{m // 60}:{m % 60:02d}"


def tickets(rule, tapes):
    r = M.run(tapes, rule, "ordinary", details=True); out = []
    by = {t.day: t for t in tapes}
    for d in r["days"]:
        t = by[d["day"]]
        for p in d["positions"]:
            out.append(dict(day=p["day"], key=(p["day"], int(p["decision_i"]), int(p["direction"])), side="P" if p["direction"] < 0 else "C",
                            minute=int(t.minute[p["decision_i"]]), lots=p["lots"], entry=p["entry"], net=p["net"], origin=p.get("origin", "E032"),
                            peak=round(p["peak"] / p["entry"], 2), path="+".join(e["reason"] for e in p["events"][1:]) or ("UNRESOLVED" if p.get("unresolved") else "")))
    return r["summary"]["net"], out


def table(ts, key):
    g = defaultdict(lambda: [0, 0, 0.])
    for x in ts:
        k = key(x); g[k][0] += 1; g[k][1] += x["net"] > 0; g[k][2] += x["net"]
    return {k: dict(tickets=v[0], winners=v[1], net=round(v[2], 2)) for k, v in sorted(g.items())}


def window(m):return "13:00-13:30" if m < 810 else "13:30-14:00" if m < 840 else "14:00-14:30" if m < 870 else "14:30-15:00"


def main():
    E.directions = C.masked; M.AVAIL = C.available_at
    try:
        T = M.tapes(); res = {}
        base = {y: tickets(M.E032, T[y])[1] for y in (2023, 2024, 2025)}
        for name, (extra, years) in ARMS.items():
            arm = {}
            for y in years:
                net, ts = tickets(replace(M.E032, **extra), T[y])
                assert abs(net - SAVED[(name, y)]) < .01, (name, y, net, SAVED[(name, y)])
                ctl = {x["key"]: x for x in base[y]}; mine = {x["key"]: x for x in ts}
                added = [x for k, x in mine.items() if k not in ctl]; removed = [x for k, x in ctl.items() if k not in mine]
                changed = [(x, ctl[k]) for k, x in mine.items() if k in ctl and abs(x["net"] - ctl[k]["net"]) > .005]
                arm[y] = dict(net=net, tickets=len(ts), winners=sum(x["net"] > 0 for x in ts),
                              by_side=table(ts, lambda x: x["side"]), by_exit=table(ts, lambda x: x["path"]), by_window=table(ts, lambda x: window(x["minute"])),
                              by_origin=table(ts, lambda x: x["origin"]),
                              best=sorted(ts, key=lambda x: -x["net"])[:3], worst=sorted(ts, key=lambda x: x["net"])[:3],
                              vs_control=dict(added=len(added), added_net=round(sum(x["net"] for x in added), 2), added_winners=sum(x["net"] > 0 for x in added),
                                              removed=len(removed), removed_net=round(sum(x["net"] for x in removed), 2),
                                              changed=len(changed), changed_delta=round(sum(a["net"] - b["net"] for a, b in changed), 2),
                                              biggest=sorted([dict(day=a["day"], side=a["side"], was=b["net"], now=a["net"]) for a, b in changed], key=lambda z: abs(z["now"] - z["was"]), reverse=True)[:3]))
            res[name] = arm
            print(name, {y: (v["net"], v["tickets"], v["vs_control"]["added"], v["vs_control"]["removed"], v["vs_control"]["changed"]) for y, v in arm.items()}, flush=True)
    finally:
        E.directions = C.ORIGINAL; M.AVAIL = None
    for arm in res.values():
        for v in arm.values():
            for k in ("best", "worst"):
                for x in v[k]: x.pop("key", None)
    (HERE / "anatomy.json").write_text(json.dumps({k: {str(y): v for y, v in a.items()} for k, a in res.items()}, indent=1, default=str) + "\n", encoding="utf-8")
    print("ANATOMY_OK totals match the scored results")


if __name__ == "__main__":
    main()
