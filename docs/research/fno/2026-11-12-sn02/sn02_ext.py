"""SN02-A: the owner's SN01 wallet on N11's own entries (research only).

SN01 found no entry of its own that beats costs. The owner points at the paper main book (N11/N012) as the system's
profitable strategy. This module takes N11's stored one-year replays (docs/research/simulation/2026-11-02-fno-n11,
the panel book "N11", one per seen NIFTY year) as a stream of entries - contract, entry minute, exit minute - and plays
them inside SN01's fixed wallet with the owner's day target, day loss limit and lock.

Caveat stated before any number: N11 was shaped on all four of these years (2023 was N08's exam and N11 came after
it). Everything here is in-sample for the ENTRY. Only the overlay (target / lock / wallet) is new, and it has few
settings. N11's entries depend on its own sized-book state (brakes, stand-aside, one or two positions); they are used
as a fixed list.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SN01 = HERE.parent / "2026-11-12-sn01"
sys.path[:0] = [str(HERE), str(SN01)]

import sn01_data as D  # noqa: E402
import sn01_sim as M  # noqa: E402

ROOT = M.ROOT
N11 = ROOT / "docs/research/simulation/2026-11-02-fno-n11"
YEARS = ("2023", "2024", "2025", "2026")


def minute_of(stamp: str) -> int:
    return int(stamp[11:13]) * 60 + int(stamp[14:16]) - (9 * 60 + 15)


def n11_trades(year: str) -> list[dict]:
    key = json.loads((N11 / f"_local/keys-panel-{year}.json").read_text(encoding="utf-8"))["N11"]
    data = json.loads((N11 / f"_local/evals/{key}.json").read_text(encoding="utf-8"))
    out = []
    for t in data["trades"]:
        ctx = t["n091_entry"]["native_gate_context"]
        sym = t["tradingsymbol"]
        expiry = f"20{sym[5:7]}-{sym[7:9]}-{sym[9:11]}"
        out.append({"day": t["entry_time"][:10], "i": minute_of(t["entry_time"]), "j": minute_of(t["exit_time"]),
                    "strike": int(round(ctx["strike"])), "opt": "CE" if ctx["is_call"] else "PE", "expiry": expiry,
                    "n11_entry": t["entry_premium"], "n11_exit": t["exit_premium"], "n11_reason": t["exit_reason"],
                    "n11_net_per_lot": t["net_pnl"] / max(1, t["lots_at_exit"]), "n11_extra": t["extra_cost"],
                    "adds": t["adds"], "expert": t["entry_expert"]})
    return out


def play_day(S: M.Session, sigs: list[dict], v: dict, wallet: float, target: float, loss: float,
             stress: float, record: bool = False) -> dict:
    """v: {"exit": "n11" | "sell" | "lock", "give": float, "max_lots": int, "cash": float, "otm_fallback": bool}."""
    realized, trades, n, skipped = 0.0, [], 0, []
    free_from = 0
    end = "signals_done"
    for sg in sorted(sigs, key=lambda x: x["i"]):
        if sg["i"] < free_from or sg["i"] >= M.EXIT_MIN:
            skipped.append("busy")
            continue
        if sg["expiry"] != S.s["expiry"]:
            skipped.append("other_expiry")
            continue
        i = sg["i"]
        strike, opt = sg["strike"], sg["opt"]
        rec = S.option(strike, opt)
        ok = rec is not None and rec[6][i]
        ask = M.ask_of(float(rec[0][3][i])) if ok else None
        lots = int(min(v["max_lots"], math.floor(wallet * v["cash"] / (ask * M.LOT)))) if ok else 0
        if ok and lots < 1 and v.get("otm_fallback"):
            strike = strike + (M.STEP if opt == "CE" else -M.STEP)
            rec = S.option(strike, opt)
            ok = rec is not None and rec[6][i]
            ask = M.ask_of(float(rec[0][3][i])) if ok else None
            lots = int(min(v["max_lots"], math.floor(wallet * v["cash"] / (ask * M.LOT)))) if ok else 0
        if not ok:
            skipped.append("no_quote")
            continue
        if lots < 1:
            skipped.append("wallet_too_small")
            continue
        a, b_open, b_high, b_low, b_close, b_mark, traded = rec
        qty = lots * M.LOT
        room = loss + realized
        est = M.charges(ask, ask, qty) + stress * lots
        day_stop = M._ceil_tick(ask - (room - est) / qty)
        day_tgt = ask + (target - realized + est) / qty
        for _ in range(2):
            day_tgt = ask + (target - realized + M.charges(ask, day_tgt, qty) + stress * lots) / qty
        day_tgt = M._ceil_tick(day_tgt)
        j_exit = min(max(sg["j"], i + 1), M.EXIT_MIN)
        locked, floor, peak = False, -np.inf, ask
        exit_px, reason, j = None, None, i
        for j in range(i + 1, M.EXIT_MIN + 1):
            if traded[j]:
                bo, bh, bl, bc = b_open[j], b_high[j], b_low[j], b_close[j]
                stop_eff = max(day_stop, floor)
                if bl <= stop_eff:
                    exit_px = min(stop_eff, bo)
                    reason = "lock_floor" if locked else "day_loss"
                    break
                if not locked and v["exit"] in ("sell", "lock") and bh >= day_tgt:
                    if v["exit"] == "sell":
                        exit_px, reason = max(day_tgt, bo), "day_target"
                        break
                    locked, floor, peak = True, day_tgt, max(peak, bh)
                    if bc < floor:
                        exit_px, reason = floor, "lock_floor"
                        break
                if locked:
                    floor = max(floor, max(peak, bc) - v["give"] * target / qty)
                peak = max(peak, bc)
            if not locked and j >= j_exit:
                exit_px = b_close[j] if traded[j] else b_mark[j]
                reason = "n11_exit:" + sg["n11_reason"]
                break
            if j == M.EXIT_MIN:
                exit_px = b_close[j] if traded[j] else b_mark[j]
                reason = "eod"
                break
        exit_px = float(exit_px)
        net = (exit_px - ask) * qty - M.charges(ask, exit_px, qty) - stress * lots
        realized += net
        n += 1
        free_from = j + 1
        if record:
            trades.append({"day": S.day, "i": i, "j": j, "strike": strike, "opt": opt, "lots": lots, "entry": ask,
                           "exit": exit_px, "net": round(net, 2), "reason": reason, "n11_entry": sg["n11_entry"],
                           "n11_exit": sg["n11_exit"], "n11_net_per_lot": sg["n11_net_per_lot"], "expert": sg["expert"]})
        if locked or realized >= target - 1e-6:
            end = "target"
            break
        if loss + realized < loss * 0.05:
            end = "loss_limit"
            break
    return {"day": S.day, "net": realized, "trades": n, "end": end if n else "no_trade", "skipped": skipped,
            "detail": trades}


class Year:
    def __init__(self, year: str):
        self.year = year
        self.sessions = {d: M.Session(s) for d, s in D.load_year(year)["sessions"].items()}
        self.sigs: dict[str, list] = {}
        for t in n11_trades(year):
            self.sigs.setdefault(t["day"], []).append(t)

    def ordered(self):
        return [self.sessions[d] for d in sorted(self.sessions)]
