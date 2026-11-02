"""The frozen tests, T1 to T5. September is read only after the freeze is verified and T1-T4 are on disk."""
from __future__ import annotations

import json
from dataclasses import replace

import arms as M
import e011_lab as L
import freeze as F
import panel as P
import seen_table as T
import sept as Z

OUT = L.HERE / "results.json"
KEYS = L.recorded_keys()
RAW_CLOCK = [d for d, _ in KEYS if d != "2026-10-06"]
UNDERLYING = dict(KEYS)


def stats(rows: list[tuple[str, float]]) -> dict:
    daily = [v for _, v in rows]
    total = peak = fall = 0.0
    for v in daily:
        total += v
        peak = max(peak, total)
        fall = max(fall, peak - total)
    by: dict[str, float] = {}
    for d, v in rows:
        by[UNDERLYING[d]] = by.get(UNDERLYING[d], 0.0) + v
    return dict(net=round(total, 2), worst=round(min(daily), 2), drawdown=round(fall, 2), without_best=round(total - max(daily), 2), by=by)


def profit_route(a: dict, b: dict) -> dict:
    """score_e01.py's profit route, the same tests and the same tolerance."""
    return dict(without_best=a["without_best"] >= b["without_best"] - .01,
                index=all(a["by"][u] >= v - .01 for u, v in b["by"].items()),
                higher_net=a["net"] > b["net"] + .01, worst=a["worst"] >= b["worst"] - .01,
                drawdown=a["drawdown"] <= b["drawdown"] + .01)


def t1(seen: dict) -> dict:
    out = {}
    days = [d for d, _ in KEYS]
    for name in M.PRIMARY:
        checks = {}
        for scenario in ("ordinary", "adverse"):
            for label, group in (("all8", days), ("raw7", RAW_CLOCK)):
                rows = lambda arm: [(d, seen[arm][scenario]["per"][days.index(d)]) for d in group]
                checks[f"{scenario}|{label}"] = profit_route(stats(rows(name)), stats(rows("E01")))
        out[name] = dict(checks=checks, passed=all(all(c.values()) for c in checks.values()))
    return out


def t2(seen: dict) -> dict:
    out = {}
    base = seen["E01"]["ordinary"]
    for name, near in {"E011": ("E011_S20", "E011_S30", "E011_K50"), "E011R": ("E011R_S20", "E011R_S30", "E011R_K50")}.items():
        rows = {n: dict(net=seen[n]["ordinary"]["net"], worst=seen[n]["ordinary"]["worst"],
                        passed=seen[n]["ordinary"]["net"] >= base["net"] - .01 and seen[n]["ordinary"]["worst"] >= base["worst"] - .01) for n in near}
        out[name] = dict(rows=rows, passed=all(r["passed"] for r in rows.values()))
    return out


def t3() -> dict:
    out = {"delays": {}}
    for delay in (1, 2, 3):
        row = {}
        for name in ("E01", *M.PRIMARY):
            row[name] = round(sum(L.net(L.run_c(L.Recorded(d, u), replace(M.ARMS[name], delay=delay), "X")) for d, u in KEYS), 2)
        out["delays"][str(delay * 10)] = row
    for name in M.PRIMARY:
        out[name] = all(v[name] > v["E01"] for v in out["delays"].values())
    return out


def every_break(ticket: L.Ticket, adverse: bool) -> list[dict]:
    rows = []
    for d, u in KEYS:
        S = L.Recorded(d, u, adverse)
        state, signals = L.signal_stream(S)
        for k, (i, direction) in enumerate(signals):
            S._signals[L.NATIVE_SIGNAL] = (state, [(i, direction)])
            positions = L.run_c(S, ticket, "X")
            if positions:
                p = positions[0]
                rows.append(dict(day=d, at=S.clock[i].isoformat()[:8], dir=direction, symbol=p["symbol"], entry=p["entry_price"], lots=p["lots"],
                                 net=L.net(positions), peak=p["peak"]))
    return rows


def t4() -> dict:
    out = {}
    for scenario, adverse in (("ordinary", False), ("adverse", True)):
        out[scenario] = {name: every_break(M.ARMS[name], adverse) for name in ("E01", *M.PRIMARY)}
    summary = {}
    for name in ("E01", *M.PRIMARY):
        summary[name] = {s: dict(total=round(sum(r["net"] for r in out[s][name]), 2), tickets=len(out[s][name]),
                                 worst=min(r["net"] for r in out[s][name])) for s in out}
    verdict = {name: all(summary[name][s]["total"] >= summary["E01"][s]["total"] - .01 for s in out) for name in M.PRIMARY}
    return dict(summary=summary, passed=verdict, tickets=out["ordinary"])


def t5() -> dict:
    tickets = []
    names = ("C", "E01", "STOP25", "RECOVER", "TRAIL3X", *M.PRIMARY)
    for day in Z.DAYS:
        O, A = Z.Sept(day), Z.Sept(day, adverse=True)
        for i, symbol, rule in P.admissions(O):
            row = dict(day=day, at=O.clock[i].isoformat()[:8], kind=O.kinds[symbol], rule=rule, ask=O.quote(i, symbol).ask, arms={})
            for name in names:
                a = P.run_ticket(O, i, symbol, M.ARMS[name])
                b = P.run_ticket(A, i, symbol, M.ARMS[name])
                row["arms"][name] = dict(ordinary=L.net(a) if a else None, adverse=L.net(b) if b else None,
                                         lots=a[0]["lots"] if a else 0, peak=a[0]["peak"] if a else None,
                                         events=[(e["ts"][11:19], e["action"], e["lots"], e.get("price")) for e in a[0]["_events"]] if a else [],
                                         status=a[0]["status"] if a else None)
            tickets.append(row)
    total = {n: {s: round(sum(t["arms"][n][s] or 0.0 for t in tickets), 2) for s in ("ordinary", "adverse")} for n in names}
    worst = {n: min((t["arms"][n]["ordinary"] or 0.0) for t in tickets) if tickets else 0.0 for n in names}
    verdict, named = {}, {}
    for name in M.PRIMARY:
        verdict[name] = all(total[name][s] >= total["E01"][s] - .01 for s in total[name]) and worst[name] >= worst["E01"] - .01
        named[name] = [t["day"] + " " + t["at"] for t in tickets
                       if (t["arms"]["E01"]["ordinary"] or 0) >= 1000 and (t["arms"][name]["ordinary"] or 0) < 0]
    return dict(tickets=tickets, total=total, worst=worst, passed=verdict, winners_lost=named)


def main() -> None:
    F.verify()
    print("freeze verified", flush=True)
    seen = T.table({**M.ARMS, **M.ENTRY_READINGS})
    result = dict(seen=seen, t1=t1(seen), t2=t2(seen), t3=t3(), t4=t4())
    OUT.write_text(json.dumps(result, indent=1, default=str) + "\n")
    print("T1-T4 written before September is read", flush=True)
    result["t5"] = t5()
    decision = {}
    for name in M.PRIMARY:
        decision[name] = dict(t1=result["t1"][name]["passed"], t2=result["t2"][name]["passed"], t3=result["t3"][name],
                              t4=result["t4"]["passed"][name], t5=result["t5"]["passed"][name])
        decision[name]["all"] = all(decision[name].values())
    result["decision"] = decision
    OUT.write_text(json.dumps(result, indent=1, default=str) + "\n")
    print(json.dumps(decision, indent=1))
    print(json.dumps(dict(t3=result["t3"], t4=result["t4"]["summary"], t5_total=result["t5"]["total"], t5_worst=result["t5"]["worst"], winners=result["t5"]["winners_lost"]), indent=1))


if __name__ == "__main__":
    main()
