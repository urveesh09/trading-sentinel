"""O31h exploratory causal-input/hindsight distinction, not a strategy optimizer."""
from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
PRIOR = HERE.parent / "2026-10-31-fno-complements"
sys.path.insert(0, str(PRIOR))
import lab_gap as P  # noqa: E402


def causal_inputs(frame, day, bar, direction, daily):
    """No today's daily high/low/close or future intraday rows are read."""
    past = daily[daily.index < pd.Timestamp(day)]
    now = frame[frame.index <= pd.Timestamp(bar)]
    f = P.O27F.day_features(now, date.fromisoformat(day))
    if f is None:
        raise ValueError("missing features")
    t, d = f["t"], 1 if direction == "LONG" else -1
    r = t.iloc[-1]
    pdi, mdi, adx, atr = P.W.W._dmi(past)
    rv = (past["close"] / past["close"].shift()).apply(np.log).iloc[-10:].std() * math.sqrt(252)
    first = t[t["minute"] < 585]
    box = float(first["high"].max() - first["low"].min()) if len(first) == 6 else None
    stretch = d * (r["close"] - r["vwap"]) / box if box and box > 0 else None
    path = t["close"].diff().abs().iloc[-6:].sum()
    efficiency = abs(t["close"].iloc[-1] - t["close"].iloc[-7]) / path if len(t) >= 7 and path > 0 else None
    gap = f["day_open"] - f["pdc"]
    return {"daily_dmi_with": bool((pdi.iloc[-1] > mdi.iloc[-1]) == (d > 0)),
            "daily_ema_with": bool((past["close"].iloc[-1] > past["close"].ewm(span=20, adjust=False).mean().iloc[-1]) == (d > 0)),
            "daily_adx": float(adx.iloc[-1]), "rv10": float(rv),
            "opening_range_daily_atr": box / float(atr.iloc[-1]) if box and atr.iloc[-1] > 0 else None,
            "stretch": float(stretch) if stretch is not None else None,
            "rvol": float(r["rvol"]) if pd.notna(r["rvol"]) else None,
            "efficiency6": float(efficiency) if efficiency is not None else None,
            "with_gap": bool(d * gap > 0) if gap else None,
            "minute": int(r["minute"]) + 5, "direction": direction}


def bucket(key, value):
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "MISSING"
    if key in ("daily_dmi_with", "daily_ema_with", "with_gap"):
        return "WITH" if value else "AGAINST"
    if key == "daily_adx":
        return "LT20" if value < 20 else "20_TO30"
    if key == "rv10":
        return "LT15PCT" if value < .15 else "GE15PCT"
    if key == "opening_range_daily_atr":
        return "LT_HALF_ATR" if value < .5 else "GE_HALF_ATR"
    if key == "stretch":
        return "BEHIND_VWAP" if value < 0 else ("0_TO_QUARTER" if value < .25 else "QUARTER_TO_HALF")
    if key == "rvol":
        return "LT1_5" if value < 1.5 else "GE1_5"
    if key == "efficiency6":
        return "LT_HALF" if value < .5 else "GE_HALF"
    if key == "minute":
        return "BEFORE11" if value < 660 else "FROM11"
    return value


def aggregate(rows):
    daily, months = defaultdict(float), defaultdict(float)
    for r in rows:
        daily[r["day"]] += r["net"]
        months[r["day"][:7]] += r["net"]
    total = sum(r["net"] for r in rows)
    return {"trades": len(rows), "wins": sum(r["net"] > 0 for r in rows), "net": round(total, 2),
            "before_extra_200": round(total + 200 * len(rows), 2),
            "without_best_day": round(total - max([0., *daily.values()]), 2),
            "best_day": round(max([0., *daily.values()]), 2), "worst_day": round(min([0., *daily.values()]), 2),
            "monthly": {k: round(v, 2) for k, v in sorted(months.items())}}


def run():
    P.O27F.deny_network()
    P.Y.speedups()
    year, dataset = P.YEAR, P.Y.dataset("year")
    daily = P.daily_bars()
    keys = json.loads((PRIOR / f"_local/keys-{year}.json").read_text())
    con = dataset._connect()
    rows, frames, hindsight = [], {}, {}
    for family in P.FAMILIES:
        trades = json.loads((PRIOR / "_local/evals" / f"{keys['RAW|' + family]}.json").read_text())["trades"]
        for tr in trades:
            day = tr["entry_time"][:10]
            dt = date.fromisoformat(day)
            expiry = dataset.front_expiry(dt)
            if day not in frames:
                frames[day] = dataset.futures_frame(dataset.future_contract(expiry).token, dt)
            frame = frames[day]
            feature = causal_inputs(frame, day, tr["bar_ts"], tr["direction"], daily)
            cut = pd.Timestamp(tr["bar_ts"])
            mutated = frame.copy()
            mutated.loc[mutated.index > cut, ["open", "high", "low", "close"]] *= 2
            later_daily = daily.copy()
            later_daily.loc[later_daily.index >= pd.Timestamp(day), :] *= 2
            P.O27F._FEATURES.clear()
            again = causal_inputs(mutated, day, tr["bar_ts"], tr["direction"], later_daily)
            assert feature == again, (family, day, "noncausal input")
            # Exit-minute close is hindsight attribution, never an entry feature.
            q = con.execute("SELECT close FROM candles WHERE kind='future' AND expiry=? AND datetime<=? AND datetime>=? ORDER BY datetime DESC LIMIT 1",
                            (expiry.isoformat(), tr["exit_time"][:19].replace("T", " "), day + " 09:15:00")).fetchone()
            sign = 1 if tr["direction"] == "LONG" else -1
            move = sign * (float(q[0]) - tr["entry_underlying"]) if q else None
            if day not in hindsight:
                b = con.execute("SELECT open,high,low,close FROM candles WHERE kind='future' AND expiry=? AND datetime LIKE ? ORDER BY datetime",
                                (expiry.isoformat(), day + "%")).fetchall()
                width = max(x[1] for x in b) - min(x[2] for x in b)
                progress = abs(b[-1][3] - b[0][0]) / width if width > 0 else 0
                hindsight[day] = "TREND" if progress >= .5 else "TWO_WAY"
            net = float(tr["net_pnl"]) - 200.
            rows.append({"family": family, "day": day, "bar_ts": tr["bar_ts"], "entry_time": tr["entry_time"],
                         "net": net, "gross": tr["gross_pnl"], "exit_reason": tr["exit_reason"], "underlying_move": move,
                         "inputs": feature, "hindsight_session": hindsight[day]})
    con.close()
    P.write(HERE / f"_local/diagnosis-{year}.json", rows)
    print("causal diagnostics", year, len(rows), "trade inputs, prefix/tail checks pass", flush=True)


def report():
    rows = sum((json.loads((HERE / f"_local/diagnosis-{y}.json").read_text()) for y in ("2024", "2025", "2026")), [])
    out = {"status": "EXPLORATORY_SEEN_DATA_NOT_QUALIFICATION", "entry_features_prefix_checked": len(rows), "families": {}}
    for fam in P.FAMILIES:
        part = [r for r in rows if r["family"] == fam]
        by_year = {y: aggregate([r for r in part if r["day"].startswith(y)]) for y in ("2024", "2025", "2026")}
        inputs = {}
        for key in part[0]["inputs"]:
            labels = sorted({bucket(key, r["inputs"][key]) for r in part})
            inputs[key] = {label: {y: aggregate([r for r in part if r["day"].startswith(y) and bucket(key, r["inputs"][key]) == label])
                                   for y in ("2024", "2025", "2026")} for label in labels}
        out["families"][fam] = {"years": by_year, "entry_known_buckets": inputs,
            "hindsight": {label: {y: aggregate([r for r in part if r["day"].startswith(y) and r["hindsight_session"] == label]) for y in ("2024", "2025", "2026")}
                          for label in ("TREND", "TWO_WAY")},
            "underlying_right_but_net_loss": aggregate([r for r in part if r["underlying_move"] is not None and r["underlying_move"] > 0 and r["net"] < 0]),
            "winners": aggregate([r for r in part if r["net"] > 0]), "losers": aggregate([r for r in part if r["net"] <= 0]),
            "gross_positive_but_net_negative": aggregate([r for r in part if r["gross"] > 0 and r["net"] < 0]),
            "underlying_right_but_option_gross_negative": aggregate([r for r in part if r["underlying_move"] is not None and r["underlying_move"] > 0 and r["gross"] < 0]),
            "exit_reasons": dict(Counter(r["exit_reason"] for r in part)),
            "best_five": [{k: r[k] for k in ("day", "entry_time", "net", "exit_reason", "underlying_move", "inputs")} for r in sorted(part, key=lambda r: r["net"], reverse=True)[:5]]}
    P.write(HERE / "diagnosis.json", out)
    stability = {"status": "EXPLORATORY_SUBSETS_NOT_REPLAYS_OR_FRESH_HOLDOUTS", "families": {}}
    years = ("2024", "2025", "2026")
    for fam, body in out["families"].items():
        cells = {f"{field}|{label}": values for field, labels in body["entry_known_buckets"].items()
                 for label, values in labels.items() if label != "MISSING"}
        enough_all = [n for n, v in cells.items() if all(v[y]["trades"] >= 8 for y in years)]
        positive_all = [n for n, v in cells.items() if all(v[y]["net"] > 0 for y in years)]
        folds = {}
        for hold in years:
            fit = [y for y in years if y != hold]
            eligible = {n: v for n, v in cells.items() if all(v[y]["net"] > 0 and v[y]["trades"] >= 8 for y in fit)}
            pick = max(eligible, key=lambda n: min(eligible[n][y]["net"] / eligible[n][y]["trades"] for y in fit)) if eligible else None
            folds[hold] = {"pick_from_other_two": pick, "eligible_conditions": len(eligible),
                           "held_year_subset": eligible[pick][hold] if pick else None,
                           "note": "No fit means no proposed condition; never relabel no fit as a profitable test"}
        stability["families"][fam] = {"conditions_described": len(cells), "adequate_sample_each_year": enough_all,
                                       "positive_each_year": positive_all, "two_year_selection": folds}
    P.write(HERE / "conditional-stability.json", stability)
    print(json.dumps({k: {"years": v["years"], "best_five": v["best_five"]} for k, v in out["families"].items()}, indent=1))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        report()
    else:
        run()
