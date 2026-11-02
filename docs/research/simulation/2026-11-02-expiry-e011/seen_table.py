"""The frozen arms on the eight seen sessions, whole book: A + B + the arm's ticket. Written before September is opened."""
from __future__ import annotations

import json
import sys

import arms as M
import e011_lab as L

KEYS = L.recorded_keys()


def book(adverse: bool):
    out = {}
    plays = {}
    for day, u in KEYS:
        S = L.Recorded(day, u, adverse)
        plays[day] = L.net(L.run_a(S)) + L.net(L.run_b(S))
    return plays


def stats(daily: list[float]) -> dict:
    total = peak = fall = 0.0
    for v in daily:
        total += v
        peak = max(peak, total)
        fall = max(fall, peak - total)
    return dict(net=round(total, 2), worst=round(min(daily), 2), without_best=round(total - max(daily), 2), drawdown=round(fall, 2),
                up=sum(v > .01 for v in daily), down=sum(v < -.01 for v in daily))


def table(names: dict) -> dict:
    result = {}
    days = [d for d, _ in KEYS]
    for adverse in (False, True):
        ab = book(adverse)
        for name, ticket in names.items():
            tickets = {d: L.net(L.run_c(L.Recorded(d, u, adverse), ticket, "X")) for d, u in KEYS}
            daily = [round(ab[d] + tickets[d], 2) for d in days]
            row = stats(daily) | dict(ticket_net=round(sum(tickets.values()), 2), per=daily, ticket_per=[tickets[d] for d in days])
            result.setdefault(name, {})["adverse" if adverse else "ordinary"] = row
    return result


def main(path=None):
    result = table({**M.ARMS, **M.ENTRY_READINGS})
    base = result["E01"]["ordinary"]
    print("days", [d[5:] for d, _ in KEYS])
    for name, r in result.items():
        o, a = r["ordinary"], r["adverse"]
        print(f"{name:13s} book {o['net']:9.0f} ({o['net']-base['net']:+6.0f}) adv {a['net']:9.0f} worst {o['worst']:7.0f} exbest {o['without_best']:7.0f} fall {o['drawdown']:6.0f} up/dn {o['up']}/{o['down']} ticket {o['ticket_net']:8.0f} | " + " ".join(f"{x:6.0f}" for x in o["per"]))
    if path:
        open(path, "w").write(json.dumps(result, indent=1) + "\n")
    return result


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
