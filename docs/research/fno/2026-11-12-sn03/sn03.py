"""SN03 - improving the SN02 benchmark inside the owner's Rs 15,000 wallet (research only).

Benchmark (SN02): N11's stored entries and exits, one lot, the strike one step further out of the money when a lot
costs more than the wallet, one position at a time, Rs 3,000 day limit, no 10% cap, +Rs 205 per lot per trade.

Concepts, each a small family of variants, each chosen on three years and scored on the fourth (leave one year out):
  B  entry filters known at entry (strategy, side, time, premium, days to expiry, the ADX gate)
  C  exit changes that aim at fewer losing days (breakeven stop, quick profit, giveback trail, hard premium stop)
  D  more trading days: other N11-family entry streams stored by the N11 study (NO_STAND, R0.85, N15, ...)
  E  the chosen B + C + D together
  A  the wallet: growth stopped after step k, for k = 0 .. 10
Everything is in-sample for the entries (N11 was shaped on these years). Selection luck is measured by the held-out
year; a filter is also compared with dropping the same share of trades at random.
"""
from __future__ import annotations

import json
import math
import random
import sys
from datetime import date
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-11-12-sn02"), str(HERE.parent / "2026-11-12-sn01")]

import sn01_data as D  # noqa: E402
import sn01_sim as M  # noqa: E402

N11 = M.ROOT / "docs/research/simulation/2026-11-02-fno-n11"
YEARS = ("2023", "2024", "2025", "2026")
STRESS = 205.0
WALLET = 15000.0


def minute_of(stamp: str) -> int:
    return int(stamp[11:13]) * 60 + int(stamp[14:16]) - (9 * 60 + 15)


def stream(year: str, book: str = "N11") -> list[dict]:
    key = json.loads((N11 / f"_local/keys-panel-{year}.json").read_text(encoding="utf-8"))[book]
    data = json.loads((N11 / f"_local/evals/{key}.json").read_text(encoding="utf-8"))
    out = []
    for t in data["trades"]:
        ctx = t["n091_entry"]["native_gate_context"]
        sym = t["tradingsymbol"]
        out.append({"day": t["entry_time"][:10], "i": minute_of(t["entry_time"]), "j": minute_of(t["exit_time"]),
                    "strike": int(round(ctx["strike"])), "opt": "CE" if ctx["is_call"] else "PE",
                    "expiry": f"20{sym[5:7]}-{sym[7:9]}-{sym[9:11]}", "reason": t["exit_reason"],
                    "expert": t["entry_expert"], "gate": t.get("entry_gate") or "", "book": book,
                    "sig_key": (t["entry_time"][:16], int(round(ctx["strike"])), ctx["is_call"])})
    return out


class Year:
    def __init__(self, year: str):
        self.year = year
        self.sessions = {d: M.Session(s) for d, s in D.load_year(year)["sessions"].items()}
        self.streams: dict[str, dict] = {}

    def sigs(self, book: str) -> dict:
        if book not in self.streams:
            by = {}
            for t in stream(self.year, book):
                by.setdefault(t["day"], []).append(t)
            self.streams[book] = by
        return self.streams[book]

    def ordered(self):
        return [self.sessions[d] for d in sorted(self.sessions)]


def merged(Y: Year, books: tuple) -> dict:
    """Entries from several books: the first book's signals, then any other book's signal not already present."""
    out, seen = {}, set()
    for b in books:
        for day, sigs in Y.sigs(b).items():
            for s in sigs:
                if s["sig_key"] in seen:
                    continue
                seen.add(s["sig_key"])
                out.setdefault(day, []).append(s)
    return out


def keep(sig: dict, S: M.Session, f: dict | None) -> bool:
    if not f:
        return True
    k, v = f["kind"], f["value"]
    if k == "expert_not":
        return sig["expert"] not in v
    if k == "expert_only":
        return sig["expert"] in v
    if k == "side":
        return sig["opt"] == v
    if k == "before":
        return sig["i"] < v
    if k == "after":
        return sig["i"] >= v
    if k == "dte_min":
        return (date.fromisoformat(S.s["expiry"]) - date.fromisoformat(S.day)).days >= v
    if k == "dte_max":
        return (date.fromisoformat(S.s["expiry"]) - date.fromisoformat(S.day)).days <= v
    if k == "gate":
        return v in sig["gate"]
    if k == "random_drop":
        rng = random.Random(f"{f['seed']}|{sig['day']}|{sig['i']}")
        return rng.random() >= v
    raise ValueError(k)


def play_day(S: M.Session, sigs: list, v: dict, wallet: float, loss: float, stress: float = STRESS,
             record: bool = False) -> dict:
    """v: exit tweaks {"be": Rs, "tp": Rs, "trail_at": Rs, "trail_give": share, "hard": premium share,
    "day_target": Rs or None}; v["filter"] an entry filter; one lot unless v["lots"]."""
    realized, n, trades, free_from = 0.0, 0, [], 0
    for sg in sorted(sigs, key=lambda x: x["i"]):
        if sg["i"] < free_from or sg["i"] >= M.EXIT_MIN or sg["expiry"] != S.s["expiry"]:
            continue
        if not keep(sg, S, v.get("filter")):
            continue
        if v.get("day_target") is not None and realized >= v["day_target"]:
            break
        i, strike, opt = sg["i"], sg["strike"], sg["opt"]
        if v.get("offset"):
            strike = strike + v["offset"] * (M.STEP if opt == "CE" else -M.STEP)
        lots_cap = v.get("lots", 1)
        rec, ask, lots = None, None, 0
        for attempt in range(2):
            rec = S.option(strike, opt)
            if rec is None or not rec[6][i]:
                rec = None
                break
            ask = M.ask_of(float(rec[0][3][i]))
            lots = int(min(lots_cap, math.floor(wallet / (ask * M.LOT))))
            if lots >= 1 or attempt == 1:
                break
            strike = strike + (M.STEP if opt == "CE" else -M.STEP)
        if rec is None or lots < 1:
            continue
        a, b_open, b_high, b_low, b_close, b_mark, traded = rec
        if v.get("confirm_d"):
            d = v["confirm_d"]
            if i + d >= M.EXIT_MIN or not traded[i + d] or b_close[i + d] < ask * (1 + v.get("confirm_x", 0.0)):
                continue
            i = i + d
            ask = M.ask_of(float(a[3][i]))
            lots = int(min(lots_cap, math.floor(wallet / (ask * M.LOT))))
            if lots < 1:
                continue
        qty = lots * M.LOT
        cost_at = lambda px: M.charges(ask, px, qty) + stress * lots  # noqa: E731
        room = loss + realized
        day_stop = M._ceil_tick(ask - (room - cost_at(ask)) / qty)
        stops = [day_stop]
        if v.get("hard"):
            stops.append(M._ceil_tick(ask * (1 - v["hard"])))
        # price at which this trade nets +x rupees after its own charges
        net_px = lambda x: M._ceil_tick(ask + (x + cost_at(ask + x / qty)) / qty)  # noqa: E731
        tp_px = net_px(v["tp"]) if v.get("tp") else np.inf
        be_trig = net_px(v["be"]) if v.get("be") else np.inf
        be_px = net_px(0.0)
        tr_trig = net_px(v["trail_at"]) if v.get("trail_at") else np.inf
        j_exit = min(max(sg["j"], i + 1), M.EXIT_MIN)
        be_on, tr_on, peak = False, False, ask
        exit_px, reason, j = None, None, i
        for j in range(i + 1, M.EXIT_MIN + 1):
            if traded[j]:
                bo, bh, bl, bc = b_open[j], b_high[j], b_low[j], b_close[j]
                stop = max(stops)
                if be_on:
                    stop = max(stop, be_px)
                if tr_on:
                    stop = max(stop, peak - v["trail_give"] * (peak - ask))
                if bl <= stop:
                    exit_px, reason = min(stop, bo), "stop"
                    break
                if bh >= tp_px:
                    exit_px, reason = max(tp_px, bo), "quick_profit"
                    break
                if bh >= be_trig:
                    be_on = True
                if bh >= tr_trig:
                    tr_on = True
                peak = max(peak, bc)
                if v.get("work_n") and j - i == v["work_n"] and bc < ask * (1 + v.get("work_x", 0.0)):
                    exit_px, reason = bc, "not_working"
                    break
            if j >= j_exit:
                exit_px = b_close[j] if traded[j] else b_mark[j]
                reason = "n11:" + sg["reason"]
                break
        exit_px = float(exit_px)
        net = (exit_px - ask) * qty - M.charges(ask, exit_px, qty) - stress * lots
        realized += net
        n += 1
        free_from = j + 1
        if record:
            trades.append({"day": S.day, "i": i, "j": j, "expert": sg["expert"], "opt": opt, "lots": lots,
                           "entry": ask, "exit": exit_px, "net": round(net, 2), "reason": reason, "book": sg["book"]})
        if loss + realized < loss * 0.05:
            break
    return {"day": S.day, "net": realized, "trades": n, "detail": trades}


def year_result(Y: Year, v: dict, books=("N11",), wallet=WALLET, stress=STRESS) -> dict:
    sigs = merged(Y, books)
    rs = [play_day(S, sigs.get(S.day, []), v, wallet, 0.2 * wallet, stress) for S in Y.ordered()]
    nets = [r["net"] for r in rs]
    return {"net": round(sum(nets)), "green": sum(1 for x in nets if x > 0), "red": sum(1 for x in nets if x < 0),
            "none": sum(1 for x in nets if x == 0), "worst": round(min(nets)), "trades": sum(r["trades"] for r in rs),
            "refilled": round(sum(-x for x in nets if x < 0)), "sessions": len(nets)}


def ledger(years: dict, v: dict, books=("N11",), cap: int = 0, stress=STRESS) -> dict:
    W, steps, prog, total, refill = WALLET, 0, 0.0, 0.0, 0.0
    days, step_days, cum, peak, fall = [], [], 0.0, 0.0, 0.0
    for y in YEARS:
        Y = years[y]
        sigs = merged(Y, books)
        for S in Y.ordered():
            lots = max(1, int(W // WALLET)) if v.get("lots_follow") else v.get("lots", 1)
            r = play_day(S, sigs.get(S.day, []), {**v, "lots": lots}, W, 0.2 * W, stress)
            x = r["net"]
            total += x
            cum += x
            peak = max(peak, cum)
            fall = max(fall, peak - cum)
            refill += max(0.0, -x)
            prog += x
            while prog >= W and steps < cap:
                prog -= W
                W *= 1.5
                steps += 1
                step_days.append([S.day, round(W)])
            days.append(x)
    return {"total": round(total), "steps": steps, "final_wallet": round(W), "step_days": step_days,
            "green": sum(1 for d in days if d > 0), "red": sum(1 for d in days if d < 0),
            "none": sum(1 for d in days if d == 0), "worst": round(min(days)), "fall": round(fall),
            "refilled": round(refill)}
