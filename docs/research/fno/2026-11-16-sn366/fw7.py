"""SN380: the follow-up chosen by the rule frozen in PLAN.md section 2, frozen forward on the tick recorder.

The rule picks, among SN366-SN379's development arms with >= 100 trades that are positive at Rs 205, the one with the
highest zero-stress net per trade: SN376's AUCTION direction bought 1-2 strikes in the money at 09:16 and held 60 minutes
(171 trades, Dec 2025 - Oct 2026: +Rs 244 gross, +Rs 67 at Rs 205, -Rs 137 at Rs 400; ATM -44, coin-flip ITM -131).
Amendment B4 (Nov 16, before any forward session is scored): the rule's clause "entered after SN371's 10:15 reset when it
is an opening signal" is dropped, because SN371 / SN376 measured that entry negative on the same development sessions
(ITM at 10:15: -Rs 697 a trade at Rs 205 over 60 minutes); a forward test of a known loser teaches nothing.

Per recorder session (fw5's loader; its auction price A and previous close C0; g = A / C0 - 1; g = 0 -> no decision):
  ITM       the side of g, 1 strike in the money from the index at 09:16:00, 2 strikes when one lot of the 2-ITM's ask at
            09:16:00 is <= Rs 15,000; fw2's SN302 execution decided at 09:16:00; held 60 minutes, fw2's Rs 3,000 stop;
            20 minutes as a diagnostic
  ATM       the same side at the money (control)
  COIN_ITM  a seeded coin-flip side at the same depth (control)
Verdict once, on the same first 20 qualified non-expiry sessions as fw5 (SN300a's window): fw5.judge - PASS = >= 15
trades, net at Rs 205 and Rs 400 > 0, mean at Rs 205 above both controls, > 0 without the best day; < 15 = INSUFFICIENT.
`dev FOLDER` prints plumbing only.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn351"))
import fw5  # noqa: E402

fw2, tk = fw5.fw2, fw5.tk
OUT = HERE / "results-sn380.json"
TDEC, HOLD, DIAG = 60.0, 3600.0, 1200.0


def ask_at(day, tok, t):
    a = fw2.asof_ask(day, tok, t)
    return None if a is None else float(a)


def leg(day, side, atm, depth_choice=None):
    sgn = -1 if side == "CE" else 1
    for depth in ((2, 1) if depth_choice is None else (depth_choice,)):
        tok = day.opt.get((day.front, atm + sgn * depth * 50, side))
        if tok is None:
            continue
        a = ask_at(day, tok, TDEC)
        if depth == 1 or (a is not None and a * day.lot <= 15000.0):
            return tok, depth
    return None, None


def trade(day, tok, extra=None):
    if tok is None:
        return {"missed": True, "why": "no_contract"}
    r = fw2.trade(day, tok, TDEC, HOLD)
    if not r.get("missed"):
        r["diag"] = {"1200": fw2.trade(day, tok, TDEC, DIAG).get("net205"), "300": None, "3600": r.get("net205")}
    r.update(extra or {})
    return r


def session(folder):
    base = fw5.session(folder)                     # its auction reading (A, C0, g) and skips
    out = {"day": base["day"], "skip": base.get("skip")}
    if base.get("skip") or base.get("g") in (None, 0):
        out["skip"] = out["skip"] or "no_gap"
        return out
    day = fw2.Day(folder, fw5.load_open(folder))
    atm = day.atm(TDEC)
    if atm is None:
        out["skip"] = "no_index"
        return out
    side = "CE" if base["g"] > 0 else "PE"
    tok, depth = leg(day, side, atm)
    coin = random.Random(f"sn380-{base['day']}").choice(("CE", "PE"))
    ctok, cdepth = leg(day, coin, atm)
    out.update(g=base["g"], A=base["A"], C0=base["C0"], side=side, depth=depth, ITM=trade(day, tok, {"depth": depth}),
               ATM=trade(day, day.opt.get((day.front, atm, side))), COIN_ITM=trade(day, ctok, {"side": coin, "depth": cdepth}),
               persistent=base.get("persistent"), accepted=base.get("accepted"), capped=base.get("capped"), I06=base.get("I06"))
    return out


def verdict():
    if OUT.exists():
        raise SystemExit("SN380 is scored once")
    days = sorted(p.name for p in fw5.ARCH.iterdir() if p.is_dir() and p.name >= fw5.START) if fw5.ARCH.exists() else []
    rows = []
    for d in days:
        rc = fw5.REC / f"{d}.json"
        q = json.loads(rc.read_text(encoding="utf-8")).get("qualify", {}) if rc.exists() else {}
        if not q.get("ok"):
            continue
        r = session(fw5.ARCH / d)
        if r.get("skip"):
            continue
        rows.append(r)
        if len(rows) == fw5.N_SESSIONS:
            break
    if len(rows) < fw5.N_SESSIONS:
        raise SystemExit(f"{len(rows)} of {fw5.N_SESSIONS} sessions so far; the verdict waits")
    res = {"sessions": [r["day"] for r in rows], "ITM": fw5.judge(rows, "ITM", ("ATM", "COIN_ITM")), "rows": rows}
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "dev":
        r = session(Path(sys.argv[2]))
        print(json.dumps({k: r.get(k) for k in ("day", "skip", "side", "depth")} | {k: {x: r[k].get(x) for x in ("missed", "why", "latency", "status", "depth", "side")} for k in ("ITM", "ATM", "COIN_ITM") if k in r}, default=float))
    elif len(sys.argv) > 1 and sys.argv[1] == "verdict":
        verdict()
    else:
        raise SystemExit("usage: fw7.py dev FOLDER | verdict")
