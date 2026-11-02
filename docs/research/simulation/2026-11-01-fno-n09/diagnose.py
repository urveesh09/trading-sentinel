"""N09 step 1: every N08 trade at one lot, brakes off, with what was known at entry and how its path went; and one row per session.

Entry facts use only 5-minute bars closed by the entry instant, daily bars before the day and option quotes up to the entry minute. The path
fields are outcomes, used only to label a loss. Writes _local/features-YEAR.json and _local/sessions-YEAR.json.

    N08_YEAR=<year> python diagnose.py
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n09_lab as Z  # noqa: E402
import options_math  # noqa: E402
from fno_chain import RISK_FREE_RATE, years_to_expiry  # noqa: E402

N, Y, C, B, F = Z.N, Z.Y, Z.C, Z.B, Z.F
YEAR = B.YEAR
TRADING_MIN_YEAR = 252 * 375


def daily_context() -> dict:
    """day -> facts from daily bars strictly before it."""
    d = F.daily_bars()
    d = d[~d.index.duplicated(keep="last")].sort_index()
    prev = d.close.shift(1)
    tr = np.maximum.reduce([(d.high - d.low).values, (d.high - prev).abs().fillna(0).values, (d.low - prev).abs().fillna(0).values])
    atr = np.zeros(len(d))
    atr[0] = tr[0]
    for i in range(1, len(d)):
        atr[i] = atr[i - 1] + (tr[i] - atr[i - 1]) / 14
    rets = np.log(d.close).diff()
    out = {}
    for i, stamp in enumerate(d.index):
        if i < 25:
            continue
        out[stamp.date().isoformat()] = {
            "atr": float(atr[i - 1]), "atr_pct": float(atr[i - 1] / d.close.iloc[i - 1] * 100), "prev_close": float(d.close.iloc[i - 1]),
            "rv10": float(rets.iloc[i - 10:i].std() * math.sqrt(252)), "rv20": float(rets.iloc[i - 20:i].std() * math.sqrt(252)),
            "ret5": float(d.close.iloc[i - 1] / d.close.iloc[i - 6] - 1), "ret20": float(d.close.iloc[i - 1] / d.close.iloc[i - 21] - 1),
            "prev_range_atr": float((d.high.iloc[i - 1] - d.low.iloc[i - 1]) / atr[i - 2]),
        }
    return out


def closed_bars(frame, now):
    pos = int(frame.index.searchsorted(np.datetime64(now.replace(tzinfo=None) - timedelta(minutes=5)), side="right"))
    closed = frame.iloc[:pos]
    day = now.date()
    dates = closed.index.date
    return closed[dates == day], closed[dates < day]


def session_state(today, prior) -> dict:
    """Facts about the session so far."""
    if len(today) < 2:
        return {}
    typical = (today.high + today.low + today.close) / 3
    vol = today.volume.clip(lower=0)
    vwap = (typical * vol).cumsum() / vol.cumsum().replace(0, np.nan)
    side = np.sign((today.close - vwap).fillna(0).values)
    side = side[side != 0]
    moves = today.close.diff().abs().sum() + abs(today.close.iloc[0] - today.open.iloc[0])
    r = np.log(today.close).diff().dropna()
    rp = np.log(prior.close).diff().dropna().iloc[-750:] if len(prior) > 80 else None
    return {
        "er_today": float(abs(today.close.iloc[-1] - today.open.iloc[0]) / moves) if moves > 0 else None,
        "vwap_cross": int((side[1:] != side[:-1]).sum()) if len(side) > 1 else 0,
        "high_today": float(today.high.max()), "low_today": float(today.low.min()), "open_today": float(today.open.iloc[0]),
        "vol_ratio": float(r.std() / rp.std()) if rp is not None and len(r) >= 4 and rp.std() > 0 else None,
        "vwap": float(vwap.iloc[-1]) if math.isfinite(vwap.iloc[-1]) else None,
    }


def iv_of(price, forward, strike, T, is_call):
    if price <= 0 or T <= 0:
        return None
    return options_math.implied_vol(price, forward, strike, T, RISK_FREE_RATE, is_call)


def atm_read(obs, expiry) -> dict | None:
    """ATM strike, its straddle and implied vol at one observation."""
    quotes = {(q.contract.strike, q.contract.instrument_type): q for q in obs.options.values()}
    strikes = sorted({k for k, _ in quotes})
    if not strikes:
        return None
    forward = obs.future.ltp
    atm = min(strikes, key=lambda k: abs(k - forward))
    ce, pe = quotes.get((atm, "CE")), quotes.get((atm, "PE"))
    if not ce or not pe:
        return None
    T = years_to_expiry(expiry, obs.at)
    ivs = [iv_of(ce.ltp, forward, atm, T, True), iv_of(pe.ltp, forward, atm, T, False)]
    ivs = [v for v in ivs if v]
    return {"strike": atm, "straddle": ce.ltp + pe.ltp, "iv": float(np.mean(ivs)) if ivs else None, "forward": forward, "T": T}


def session_row(day: str, data, ctx: dict) -> dict | None:
    observations = data.observations(day)[0]
    if not observations:
        return None
    frame = data.futures_frame(observations[0].future.contract.token, datetime.fromisoformat(day).date())
    bars = frame[frame.index.date == datetime.fromisoformat(day).date()]
    calendar = data.option_expiries()[0]
    expiry = next((e for e in calendar if e.isoformat() >= day), None)
    if expiry is None or bars.empty:
        return None
    by_minute = {o.at.hour * 60 + o.at.minute: o for o in observations}
    start, end = by_minute.get(9 * 60 + 45), by_minute.get(15 * 60 + 10)
    row = {"day": day, "dte": (expiry - datetime.fromisoformat(day).date()).days, "expiry_day": expiry.isoformat() == day, **ctx.get(day, {})}
    r = np.log(bars.close).diff().dropna()
    row.update(open=float(bars.open.iloc[0]), close=float(bars.close.iloc[-1]), high=float(bars.high.max()), low=float(bars.low.min()),
               rv_day=float(r.std() * math.sqrt(252 * 75)) if len(r) > 10 else None)
    path = bars.close.diff().abs().sum()
    row["er_day"] = float(abs(bars.close.iloc[-1] - bars.open.iloc[0]) / path) if path > 0 else None
    if start and end:
        a = atm_read(start, expiry)
        if a:
            q0 = {(q.contract.strike, q.contract.instrument_type): q for q in start.options.values()}
            q1 = {(q.contract.strike, q.contract.instrument_type): q for q in end.options.values()}
            ce0, pe0 = q0.get((a["strike"], "CE")), q0.get((a["strike"], "PE"))
            ce1, pe1 = q1.get((a["strike"], "CE")), q1.get((a["strike"], "PE"))
            row.update(iv_0945=a["iv"], straddle_0945=a["straddle"], fut_0945=a["forward"], fut_1510=end.future.ltp)
            if ce0 and pe0 and ce1 and pe1:
                row["straddle_1510"] = ce1.ltp + pe1.ltp
                row["straddle_change_pct"] = (ce1.ltp + pe1.ltp) / (ce0.ltp + pe0.ltp) - 1
            # The move the morning's option price paid for, 09:45 to 15:10, against the move that came.
            if a["iv"]:
                row["implied_move"] = a["forward"] * a["iv"] * math.sqrt(325 / TRADING_MIN_YEAR)
                row["realised_move"] = abs(end.future.ltp - a["forward"])
                intr = bars[(bars.index.hour * 60 + bars.index.minute >= 585) & (bars.index.hour * 60 + bars.index.minute < 910)]
                rr = np.log(intr.close).diff().dropna()
                if len(rr) > 10:
                    row["rv_iv"] = float(rr.std() * math.sqrt(252 * 75) / a["iv"])
    return row


def trade_row(t: dict, data, ctx: dict, stops_today: int) -> dict:
    day = t["entry_time"][:10]
    entry, end = datetime.fromisoformat(t["entry_time"]), datetime.fromisoformat(t["exit_time"])
    observations = data.observations(day)[0]
    frame = data.futures_frame(observations[0].future.contract.token, entry.date())
    today, prior = closed_bars(frame, entry)
    sign = 1 if t["direction"] == "LONG" else -1
    risk = abs(t["entry_underlying"] - t["initial_stop_underlying"])
    daily = ctx.get(day, {})
    atr = daily.get("atr")
    state = session_state(today, prior)
    last = today.iloc[-1] if len(today) else None
    atr5 = t.get("atr_at_entry")
    row = {
        "year": YEAR, "day": day, "time": t["entry_time"][11:16], "minute": entry.hour * 60 + entry.minute, "expert": t.get("entry_expert"), "origin": t.get("origin"),
        "direction": t["direction"], "symbol": t["tradingsymbol"], "premium": t["entry_premium"], "exit": t["exit_reason"], "net": t["net_pnl"], "gross": t["gross_pnl"],
        "hold": (end - entry).total_seconds() / 60, "risk_points": risk, "stretch": t.get("stretch"), "delta": abs(t.get("delta_at_entry") or 0), "atr5": atr5,
        "adx": None, "stops_before_today": stops_today,
        **{k: daily.get(k) for k in ("atr", "atr_pct", "rv10", "rv20", "ret5", "ret20", "prev_range_atr")},
        "er_today": state.get("er_today"), "vwap_cross": state.get("vwap_cross"), "vol_ratio": state.get("vol_ratio"),
    }
    if atr and state:
        row["range_atr"] = (state["high_today"] - state["low_today"]) / atr
        row["with_day_atr"] = sign * (t["entry_underlying"] - state["open_today"]) / atr
        row["gap_with_atr"] = sign * (state["open_today"] - daily["prev_close"]) / atr
        row["risk_atr"] = risk / atr
        row["ret5_with"] = sign * daily["ret5"]
        row["ret20_with"] = sign * daily["ret20"]
    if last is not None and last.high > last.low:
        loc = (last.close - last.low) / (last.high - last.low)
        row["close_loc"] = float(loc if sign > 0 else 1 - loc)
        if atr5:
            row["bar_atr5"] = float((last.high - last.low) / atr5)
    if len(today) >= 3 and atr5:
        row["push2_atr5"] = float(sign * (today.close.iloc[-1] - today.close.iloc[-3]) / atr5)

    # Option facts at the entry minute.
    now_obs = next((o for o in observations if o.at == entry), None)
    held = [o for o in observations if entry < o.at]
    match = lambda o: next((q for q in o.options.values() if q.contract.tradingsymbol == t["tradingsymbol"]), None)  # noqa: E731
    if now_obs:
        q = match(now_obs)
        if q:
            contract = q.contract
            is_call = contract.instrument_type == "CE"
            T = years_to_expiry(contract.expiry, entry)
            forward = now_obs.future.ltp
            iv = iv_of(q.ltp, forward, contract.strike, T, is_call)
            intrinsic = max(0.0, forward - contract.strike) if is_call else max(0.0, contract.strike - forward)
            delta = row["delta"] or 0.5
            row.update(iv=iv, dte=(contract.expiry - entry.date()).days, extrinsic_pct=(q.ltp - intrinsic) / q.ltp if q.ltp > 0 else None, spread=q.ask - q.bid)
            if iv and daily.get("rv20"):
                row["iv_rv20"] = iv / daily["rv20"]
            if atr:
                row["premium_per_atr"] = t["entry_premium"] / (delta * atr)
            target_pts = risk * 1.8
            if target_pts > 0:
                row["cost_share"] = (q.ask - q.bid + (200 + 5) / 65) / (delta * target_pts)
                row["premium_per_target"] = t["entry_premium"] / (delta * target_pts)
            prior_obs = [o for o in observations if timedelta(minutes=14) <= entry - o.at <= timedelta(minutes=16)]
            if prior_obs:
                q0 = match(prior_obs[0])
                dfut = forward - prior_obs[0].future.ltp
                if q0 and abs(dfut) >= 10:
                    row["response"] = ((q.ltp - q0.ltp) / dfut) * (1 if is_call else -1) / delta
    # Outcome labels. Path after entry: index in stop-distance units, option bid against entry.
    path = []
    for o in held:
        q = match(o)
        if q is None or q.bid <= 0 or risk <= 0:
            continue
        path.append((o.at <= end, sign * (o.future.ltp - t["entry_underlying"]) / risk, q.bid))
    during = [p for p in path if p[0]]
    after = [p for p in path if not p[0]]
    row["mfe_index_r"] = max((p[1] for p in during), default=0.0)
    row["mae_index_r"] = min((p[1] for p in during), default=0.0)
    row["exit_index_r"] = during[-1][1] if during else 0.0     # the exit is the last observation of the path
    row["mfe_option"] = max((p[2] for p in during), default=t["entry_premium"]) / t["entry_premium"] - 1
    row["after_close_option"] = after[-1][2] / t["entry_premium"] - 1 if after else None
    row["after_best_option"] = max((p[2] for p in after), default=0.0) / t["entry_premium"] - 1 if after else None
    if t["net_pnl"] > 0:
        label = "WIN"
    elif t["gross_pnl"] > 0:
        label = "COST"
    elif row["exit_index_r"] > 0:
        label = "OPTION"
    elif row["mfe_index_r"] >= 0.5:
        label = "FAILED_MOVE"
    else:
        label = "WRONG_DIRECTION"
    row["label"] = label
    return row


def main() -> None:
    B.O27F.deny_network()
    B.L._init()
    keys = json.loads((Z.LOCAL / f"keys-diag-{YEAR}.json").read_text(encoding="utf-8"))
    trades = json.loads((Y.EVALS / f"{keys['DIAG']}.json").read_text(encoding="utf-8"))["trades"]
    closed = sorted((t for t in trades if "net_pnl" in t), key=lambda t: t["entry_time"])
    data = Y.dataset("year")
    ctx = daily_context()
    sessions = [r for r in (session_row(d, data, ctx) for d in data.days) if r]
    N.X.write(Z.LOCAL / f"sessions-{YEAR}.json", sessions)
    table = C.table("year")
    rows = []
    stops: dict = {}
    for t in closed:
        day = t["entry_time"][:10]
        row = trade_row(t, data, ctx, stops.get(day, 0))
        row["adx"] = (table.get(day) or {}).get("adx_value")
        rows.append(row)
        if t["exit_reason"] in ("underlying_stop", "premium_backstop"):
            stops[day] = stops.get(day, 0) + 1
    N.X.write(Z.LOCAL / f"features-{YEAR}.json", rows)
    print("features", YEAR, len(rows), "sessions", len(sessions), flush=True)


if __name__ == "__main__":
    main()
