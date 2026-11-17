"""Frozen 10:00 NIFTY challenger screen. Offline research, no orders."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from hashlib import file_digest
from pathlib import Path
import json
import math
import pickle
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
ROOT = HERE.parents[3]
sys.path[:0] = [
    str(FNO / "2026-11-16-sn251"),
    str(FNO / "2026-11-17-sn456"),
    str(FNO / "2026-11-17-sn411"),
    str(FNO / "2026-11-17-sn441"),
    str(ROOT / "python-engine"),
]
import gl  # noqa: E402
import ledger10  # noqa: E402

FUTURES = FNO / "2026-11-17-sn456/_local/fut.npz"
OPTION_CACHE = FNO / "2026-11-16-sn251/_local/gl-devall.pkl"
OUTPUT = HERE / "results.json"
DETAIL = HERE / "_local/daily-receipts.json"
LOT, ROOM, STOP, ENTRY, GRACE = 65, 15000.0, 3000.0, 45, 5
STRESSES = (205, 400)
SIDES = ("CE", "PE")
HORIZONS = (20, 60)
YEARS = ("2024", "2025", "2026")
MIN_TRAIN = 250


@dataclass(frozen=True)
class Order:
    side: str
    strike: int
    limit: float
    ask: float


@dataclass(frozen=True)
class Trade:
    state: str
    net: float
    exit_minute: int | None = None
    exit_reason: str | None = None
    debit: float = 0.0
    strike: int | None = None
    ask: float | None = None
    bid: float | None = None


SKIP = Trade("NO_SIGNAL", 0.0)


def sha(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def verify_freeze():
    freeze = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    for relative, digest in {**freeze["sha256"], **freeze["external_sha256"]}.items():
        if sha(ROOT / relative) != digest:
            raise RuntimeError(f"Frozen input changed: {relative}")
    from cost_schedules import options_cost_snapshot
    if options_cost_snapshot("NFO") != freeze["effective_nfo_costs"]:
        raise RuntimeError("Effective NFO cost inputs differ from the freeze")


def exact_contracts(path):
    with np.load(path) as z:
        dates, expiry, cube = z["days"], z["expiries"], z["ohlcv"]
    for date, expiries, contracts in zip(dates, expiry, cube):
        active = sorted(
            (str(ex), data.astype(np.float64))
            for ex, data in zip(expiries, contracts)
            if ex and ex >= date
        )
        if active:
            yield str(date), active


def log_return(later, earlier):
    return 10000.0 * math.log(later / earlier)


def futures_features():
    history, rows = [], {}
    earlier = {}
    calendar = []
    for day, contracts in exact_contracts(FUTURES):
        calendar.append(day)
        expiry, tape = contracts[0]
        # Both endpoints of prior same-clock returns must be genuine prints.
        start, finish = tape[ENTRY, 0], tape[ENTRY + 60, 0]
        future_return = log_return(finish, start) if min(start, finish) > 0 else np.nan
        next_earlier = {ex: data[374, 3] for ex, data in contracts}
        opening = tape[:ENTRY]
        opened, closed = opening[0, 0], opening[-1, 3]
        previous = earlier.get(expiry, np.nan)
        earlier = next_earlier
        eligible = (
            np.isfinite(opening).all() and np.isfinite([previous, future_return]).all()
            and min(previous, opened, closed, opening[:, 2].min()) > 0
            and (opening[:, 3] > 0).all()
        )
        if eligible and len(history) >= 20 and np.isfinite(history[-20:]).all():
            close = opening[:, 3]
            changes = np.diff(np.log(np.r_[opened, close])) * 10000.0
            gap = log_return(opened, previous)
            intraday = log_return(closed, opened)
            hi, lo = opening[:, 1].max(), opening[:, 2].min()
            variance = np.dot(changes, changes)
            base = [
                gap, intraday, log_return(closed, close[29]), log_return(closed, close[34]),
                log_return(hi, lo), math.sqrt(variance),
            ]
            volume = opening[:, 4]
            relative_volume = volume[-10:].sum() / volume.sum() if volume.sum() > 0 else np.nan
            signed_volume = np.dot(volume, np.sign(changes)) / volume.sum() if volume.sum() > 0 else np.nan
            path = [
                np.dot(np.sign(changes), changes ** 2) / max(variance, 1e-9),
                float(np.mean(close > opened)),
                (closed - lo) / max(hi - lo, 0.05),
            ]
            term = [np.nan, np.nan]
            if len(contracts) > 1:
                other = contracts[1][1]
                clocks = (14, 34, 44)  # 09:29, 09:49 and 09:59 completed bars
                if all(other[i, 3] > 0 and other[i, 4] > 0 and tape[i, 4] > 0 for i in clocks):
                    term = [
                        log_return(other[44, 3], other[i, 3]) - log_return(closed, close[i])
                        for i in clocks[:-1]
                    ]
            rows[day] = {
                "base": base, "R1": term,
                "R2": [signed_volume, relative_volume, intraday * relative_volume],
                "R3": [np.mean(history[-5:]), np.mean(history[-20:])],
                "R4": path, "target": future_return,
            }
        history.append(future_return)
    return calendar, rows


def buy_cost(ask):
    return ask * LOT + gl.wk.charges(ask, 0.0, LOT, "NFO")


def room_price():
    lo, hi = 0.0, ROOM / LOT
    for _ in range(40):
        mid = (lo + hi) / 2
        if buy_cost(mid) <= ROOM:
            lo = mid
        else:
            hi = mid
    return math.floor(lo * 20) / 20


def exact_print(series, minute, column):
    if series is None or not 0 <= minute < series.shape[1]:
        return None
    mark, volume = series[column, minute], series[4, minute]
    return float(mark) if np.isfinite(mark) and mark > 0 and np.isfinite(volume) and volume > 0 else None


def order_book(smp, session, side, affordable):
    spot = float(session["index"][3, ENTRY - 1])
    if not np.isfinite(spot) or spot <= 0 or not session["index_traded"][ENTRY - 1]:
        return None, None, [np.nan, np.nan]
    atm = gl.atm(smp, session, ENTRY - 1)
    options = session["options"]

    def mark(strike):
        return exact_print(options.get((strike, side)), ENTRY - 1, 3)

    def order(depth):
        strike = atm + (-50 if side == "CE" else 50) * depth
        px = mark(strike)
        if px is None:
            return None
        ask = gl.wk.ask(smp.mk, px)
        if buy_cost(ask) > ROOM:
            return None
        return Order(side, strike, min(round(ask + 0.10, 2), affordable), ask)

    available = {depth: order(depth) for depth in (0, 1, 2)}
    reference = available[1] or available[0]
    value = []
    for depth, current in available.items():
        if current is None:
            continue
        left, right = mark(current.strike - 50), mark(current.strike + 50)
        if left is None or right is None:
            continue
        delta = (left - right if side == "CE" else right - left) / 100.0
        if 0.2 <= delta <= 0.95:
            intrinsic = max(0.0, (spot - current.strike) * (1 if side == "CE" else -1))
            extrinsic_per_delta = max(0.0, current.ask - intrinsic) / delta
            value.append((extrinsic_per_delta, current.ask, depth, current))
    alternative = min(value)[-1] if value else reference
    atm_price = mark(atm)
    return reference, alternative, [atm_price if atm_price is not None else np.nan,
                                    reference.ask if reference is not None else np.nan]


def net_at(bid, ask, stress):
    return (bid - ask) * LOT - gl.wk.charges(ask, bid, LOT, "NFO") - stress


def execute(order, entry_minute, horizon, stress, ask_at, close_bid_at, open_bid_at):
    if order is None:
        return Trade("NO_LABEL_OR_CASH", 0.0)
    ask = ask_at(entry_minute)
    if ask is None:
        return Trade("NO_ENTRY_PRINT", 0.0)
    if ask > order.limit + 1e-9 or buy_cost(ask) > ROOM:
        return Trade("OVER_LIMIT", 0.0)

    scheduled = entry_minute + horizon
    trigger = next(
        (i for i in range(entry_minute, scheduled) if
         (bid := close_bid_at(i)) is not None and net_at(bid, ask, stress) <= -STOP),
        None,
    )
    exit_start = scheduled if trigger is None else trigger + 1
    required_debit = buy_cost(ask)
    for i in range(exit_start, scheduled + GRACE + 1):
        bid = open_bid_at(i)
        if bid is not None:
            return Trade("ENTERED", net_at(bid, ask, stress), i, "TIME" if trigger is None else "STOP",
                         required_debit, order.strike, ask, bid)
    return Trade("UNRESOLVED_LOSS_BOUND", -required_debit - stress, debit=required_debit,
                 strike=order.strike, ask=ask)


def bar_trade(smp, session, order, horizon, stress):
    candle = session["options"].get((order.strike, order.side)) if order else None

    def ask_at(i):
        px = exact_print(candle, i, 0)
        return gl.wk.ask(smp.mk, px) if px is not None else None

    def bid_at(i, column):
        px = exact_print(candle, i, column)
        return gl.wk.bid(smp.mk, px) if px is not None else None

    return execute(order, ENTRY, horizon, stress, ask_at, lambda i: bid_at(i, 3), lambda i: bid_at(i, 0))


def parity_with_old_ledger(smp, days):
    cached = json.loads(ledger10.CACHE.read_text(encoding="utf-8"))
    eligible = sorted(set(days) & set(cached))
    checks = 0
    for day in eligible[::max(1, len(eligible) // 18)]:
        for side in SIDES:
            for stress in STRESSES:
                actual = ledger10.side_trade(smp, smp.s[day], side, stress)
                expected = cached[day][side]
                state = expected["state"] if stress == 205 else expected["state400"]
                assert actual["state"] == state and actual.get("net") == expected[f"net{stress}"], (
                    day, side, stress, actual, expected
                )
                checks += 1
    return checks


def build():
    calendar, features = futures_features()
    with OPTION_CACHE.open("rb") as handle:
        smp = gl.Sample("ALL", pickle.load(handle), gl.DEV_LO, gl.TEST_HI)
    days = sorted(d for d in smp.days if d != smp.s[d]["expiry"] and d in features)
    assert all(d != smp.s[d]["expiry"] for d in days)
    parity = parity_with_old_ledger(smp, days)
    orders, io, outcomes = {}, {}, {}
    affordable = room_price()
    for day in days:
        session = smp.s[day]
        expiry_distance = (np.datetime64(session["expiry"]) - np.datetime64(day)).astype(int)
        features[day]["base"].append(int(expiry_distance))
        features[day]["option_expiry"] = session["expiry"]
        orders[day], io[day], outcomes[day] = {}, [], {}
        for side in SIDES:
            reference, alternative, premium = order_book(smp, session, side, affordable)
            io[day].extend(premium)
            orders[day][side] = reference
            for horizon in HORIZONS:
                for stress in STRESSES:
                    outcomes[day][side, horizon, stress] = bar_trade(smp, session, reference, horizon, stress)
            for stress in STRESSES:
                outcomes[day][side, "value", stress] = bar_trade(smp, session, alternative, 60, stress)
    return calendar, days, features, orders, io, outcomes, parity


def quarter(day):
    return day[:4] + str((int(day[5:7]) - 1) // 3)


def ridge(x, y, predict_on):
    mean, sd = x.mean(axis=0), x.std(axis=0)
    sd[sd < 1e-9] = 1.0
    design = (x - mean) / sd
    penalty = 10.0 * np.eye(design.shape[1])
    coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ (y - y.mean(axis=0)))
    return design @ coefficients + y.mean(axis=0), (predict_on - mean) / sd @ coefficients + y.mean(axis=0)


def fit_quarters(days, x, target):
    x, target = np.asarray(x, dtype=float), np.asarray(target, dtype=float)
    date_array = np.asarray(days)
    complete = np.isfinite(x).all(axis=1)
    if target.ndim == 1:
        trainable = complete & np.isfinite(target)
    else:
        trainable = complete & np.isfinite(target).all(axis=1)
    quarters = np.asarray([quarter(day) for day in days])
    scores = {}
    for window in sorted(set(quarters)):
        if window[:4] not in YEARS:
            continue
        earlier = (quarters < window) & trainable
        test = (quarters == window) & complete
        if earlier.sum() < MIN_TRAIN or not test.any():
            continue
        assert max(date_array[earlier]) < min(date_array[test])
        fitted, predicted = ridge(x[earlier], target[earlier], x[test])
        confidence = float(np.quantile(np.abs(fitted), 0.70)) if fitted.ndim == 1 else None
        for day, score in zip(date_array[test], predicted):
            scores[str(day)] = (score, confidence)
    return scores


def direction(score, cutoff):
    if score == 0.0 or abs(score) < cutoff:
        return None
    return ("CE" if score > 0 else "PE"), 60


def direction_review(days, features, slot):
    base = np.asarray([features[day]["base"] for day in days])
    y = np.asarray([features[day]["target"] for day in days])
    augmented = np.asarray([features[day][slot] for day in days])
    match = np.isfinite(augmented).all(axis=1)
    matched_days = [day for day, usable in zip(days, match) if usable]
    models = {
        "base": fit_quarters(matched_days, base[match], y[match]),
        "augmented": fit_quarters(matched_days, np.c_[base[match], augmented[match]], y[match]),
    }
    forecast_days = sorted(models["base"])
    assert forecast_days == sorted(models["augmented"])
    if not forecast_days:
        return {}, {}, {"usable_training_and_test_dates": int(match.sum()), "predictions": 0}
    actual = np.asarray([features[day]["target"] for day in forecast_days])
    predictions = {name: np.asarray([m[day][0] for day in forecast_days]) for name, m in models.items()}
    errors = {name: np.square(actual - preds) for name, preds in predictions.items()}
    gain = errors["base"] - errors["augmented"]

    def stats(preds, se):
        return {
            "correlation": round(float(np.corrcoef(preds, actual)[0, 1]), 5),
            "sign_accuracy": round(float(np.mean(np.sign(preds) == np.sign(actual))), 5),
            "rmse_bps": round(float(np.sqrt(np.mean(se))), 5),
        }

    meta = {
        "usable_training_and_test_dates": int(match.sum()),
        "predictions": len(actual),
        **{name: stats(preds, errors[name]) for name, preds in predictions.items()},
        "paired_mse_gain_bps_squared": round(float(gain.mean()), 5),
        "paired_mse_gain_90ci": interval(gain),
        "by_year": {
            year: {"predictions": len(values), "mse_gain_bps_squared": round(float(np.mean(values)), 5)}
            for year in YEARS
            if len(values := [value for day, value in zip(forecast_days, gain) if day.startswith(year)])
        },
    }
    a = {day: direction(*score) for day, score in models["augmented"].items()}
    b = {day: direction(*score) for day, score in models["base"].items()}
    return a, b, meta


def direct_policies(days, features, orders, premium_info, outcomes):
    def inputs(day):
        f = features[day]
        premium = np.asarray(premium_info[day], dtype=float)
        valid = np.isfinite(premium)
        return [*f["base"], *f["R2"], *f["R3"], *f["R4"], *np.where(valid, premium, 0.0), *valid.astype(int)]

    arm_list = [(side, horizon) for horizon in (60, 20) for side in SIDES]
    x = [inputs(day) for day in days]
    nets = np.asarray([[outcomes[day][side, horizon, 400].net for side, horizon in arm_list] for day in days])
    non_robust = fit_quarters(days, x, nets[:, :2])
    robust = fit_quarters(days, x, np.clip(nets[:, :2], -3000, 3000))
    adaptive = fit_quarters(days, x, np.clip(nets, -3000, 3000))
    future = fit_quarters(days, x, [features[d]["target"] for d in days])

    def select(day, values):
        allowed = [i for i, (side, _) in enumerate(arm_list[:len(values)]) if orders[day][side] is not None]
        if not allowed:
            return None
        best = max(allowed, key=lambda i: values[i])
        return arm_list[best] if values[best] > 0 else None

    return (
        {day: select(day, v) for day, (v, _) in non_robust.items()},
        {day: select(day, v) for day, (v, _) in robust.items()},
        {day: select(day, v) for day, (v, _) in adaptive.items()},
        {day: direction(*score) for day, score in future.items()},
    )


def interval(values):
    values = np.asarray(values, dtype=float)
    if len(values) < 20:
        return None
    rng = np.random.default_rng(47617)
    block = 20
    starts = rng.integers(len(values), size=(2000, math.ceil(len(values) / block), 1))
    indexes = ((starts + np.arange(block)) % len(values)).reshape(2000, -1)[:, :len(values)]
    return [round(float(x), 4) for x in np.quantile(values[indexes].mean(axis=1), [0.05, 0.95])]


def comparisons(days, decisions, outcomes, stress, route=None):
    records, coin = {}, []
    for day in days:
        choice = decisions.get(day)
        if choice is None:
            records[day] = SKIP
            coin.append(0.0)
        else:
            side, horizon = choice
            instrument = route if route is not None else horizon
            records[day] = outcomes[day][side, instrument, stress]
            coin.append(float(np.mean([outcomes[day][s, instrument, stress].net for s in SIDES])))
    return records, np.asarray(coin)


def performance(records):
    if not records:
        return {"sessions": 0, "fills": 0, "net": 0.0, "per_session": None, "by_year": {}}
    days = list(records)
    values = np.asarray([x.net for x in records.values()])
    ledger = np.cumsum(np.r_[0.0, values])
    states = Counter(x.state for x in records.values())
    outcomes = Counter(x.exit_reason for x in records.values() if x.exit_reason)
    return {
        "sessions": len(days),
        "states": dict(states),
        "decisions": len(days) - states["NO_SIGNAL"],
        "fills": states["ENTERED"],
        "missing_exit": states["UNRESOLVED_LOSS_BOUND"],
        "exit_reasons": dict(outcomes),
        "max_debit": round(max(x.debit for x in records.values()), 2),
        "net": round(float(values.sum()), 2),
        "per_session": round(float(values.mean()), 2),
        "per_session_90ci": interval(values),
        "net_ex_best": round(float(values.sum() - max(0.0, values.max())), 2),
        "maximum_realized_drawdown": round(float(np.max(np.maximum.accumulate(ledger) - ledger)), 2),
        "worst_day": round(float(values.min()), 2),
        "by_year": {
            year: {
                "sessions": len(ys),
                "decisions": sum(x.state != "NO_SIGNAL" for x in ys),
                "fills": sum(x.state == "ENTERED" for x in ys),
                "net": round(sum(x.net for x in ys), 2),
            }
            for year in sorted({day[:4] for day in days})
            if (ys := [x for d, x in records.items() if d.startswith(year)])
        },
    }


def evaluate(days, arm, control, outcomes, daily, name, route=None, control_route=None):
    results = {}
    for stress in STRESSES:
        a, coin = comparisons(days, arm, outcomes, stress, route)
        b, _ = comparisons(days, control, outcomes, stress, control_route)
        difference = np.asarray([a[d].net - b[d].net for d in days])
        coin_delta = np.asarray([x.net for x in a.values()]) - coin
        results[str(stress)] = {
            "candidate": performance(a),
            "control": performance(b),
            "delta": round(float(difference.sum()), 2),
            "delta_per_session_90ci": interval(difference),
            "matched_coin_net": round(float(coin.sum()), 2),
            "edge_vs_coin_90ci": interval(coin_delta),
        }
        daily[f"{name}@{stress}"] = {
            day: {"decision": arm.get(day), "candidate": asdict(a[day]), "control": asdict(b[day])}
            for day in days if arm.get(day) is not None or control.get(day) is not None
        }
    light, heavy = (results[str(stress)]["candidate"] for stress in STRESSES)
    gates = {
        "at_least_30_fills_both": min(light["fills"], heavy["fills"]) >= 30,
        "resolved_both": light["missing_exit"] == heavy["missing_exit"] == 0,
        "positive_all_years_both": all(
            stats["by_year"][year]["net"] > 0 for stats in (light, heavy) for year in YEARS
        ),
        "154_per_session_at_205": light["per_session"] >= 154,
        "positive_without_best_at_400": heavy["net_ex_best"] > 0,
        "lower_90ci_at_400_positive": heavy["per_session_90ci"][0] > 0,
    }
    results["gates"] = gates
    results["advances"] = all(gates.values())
    return results


def quote_review(calendar_days, selected, features, orders, outcomes):
    import sn441  # import the archive loader only for the frozen reprice

    loader = sn441.qa
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    loader.EXPORT = Path(frozen["quote_export"])
    manifest = loader.manifest()
    eligible = set(calendar_days) & set(manifest["quote_days"]) - set(manifest["unsealed_days"])
    usable = sorted(day for day in eligible if day in orders and day <= "2026-10-28")
    totals, bar = {st: {} for st in STRESSES}, {st: {} for st in STRESSES}
    for day in usable:
        pick = selected.get(day)
        if pick is None:
            for stress in STRESSES:
                totals[stress][day] = bar[stress][day] = SKIP
            continue
        side, horizon = pick
        order = orders[day][side]
        option_key = ("NIFTY", features[day]["option_expiry"], order.strike, side)
        quote = loader.build_day(day)["opt"].get(option_key)
        if quote is not None:
            asks, bids = (sn441.C.walked(quote, direction) for direction in ("ask", "bid"))
            fresh = (quote["age"] >= 0) & (quote["age"] <= 5)
            asks[~fresh] = bids[~fresh] = np.nan

        def observed(series, i):
            p = series[i]
            return float(p) if np.isfinite(p) and p > 0 else None

        for stress in STRESSES:
            bar[stress][day] = outcomes[day][side, horizon, stress]
            totals[stress][day] = (
                Trade("NO_ARCHIVED_CONTRACT", 0.0) if quote is None else
                execute(order, ENTRY + 1, horizon - 1, stress,
                        lambda i: observed(asks, i), lambda i: observed(bids, i), lambda i: observed(bids, i))
            )
    return {
        "days": usable,
        "quote": {str(st): performance(totals[st]) for st in STRESSES},
        "bar_same_days": {str(st): performance(bar[st]) for st in STRESSES},
        "per_day": {
            str(st): {day: {"quote": asdict(totals[st][day]), "bar": asdict(bar[st][day])}
                      for day in usable if selected.get(day) is not None}
            for st in STRESSES
        },
    }


def gold_review(days, chosen, outcomes):
    import gold

    gold_days, times, summaries = set(), defaultdict(list), {}
    for period, years in (("2022", gold.Y22), ("2023-2026", gold.Y2326)):
        daylog, trades, _ = gold.run(years, gold.DEPLOYED, 205.0)
        summaries[period] = gold.summary(daylog, trades)
        if period == "2023-2026":
            assert summaries[period]["net"] in (850882, 850883)
        else:
            assert summaries[period]["net"] in (-15282, -15281, -15280)
        gold_days.update(d[0] for d in daylog)
        for trade in trades:
            times[trade["day"]].append((int(trade["i"]), int(trade["j"])))

    def clear(day):
        return day in gold_days and not any(i <= ENTRY - 1 < j or i == ENTRY for i, j in times[day])

    allowed = {day: choice for day, choice in chosen.items() if choice is not None and clear(day)}
    review = {}
    for stress in STRESSES:
        restricted, _ = comparisons(days, allowed, outcomes, stress)
        standalone, _ = comparisons(days, chosen, outcomes, stress)
        conflicts = [
            day for day, record in restricted.items()
            if record.state in ("ENTERED", "UNRESOLVED_LOSS_BOUND")
            and any(ENTRY < i <= (record.exit_minute if record.exit_minute is not None else 374)
                    for i, _ in times[day])
        ]
        review[str(stress)] = {
            "gold_priority_bar_diagnostic": performance(restricted),
            "standalone": performance(standalone),
            "possible_collision_days": conflicts,
        }
    return {
        "gold_baseline": summaries,
        "clear_sessions": sum(clear(day) for day in days),
        "decisions_blocked": sum(chosen.get(day) is not None and day not in allowed for day in days),
        "stress": review,
    }


def self_test():
    cap = Order("CE", 22000, 100.1, 100)
    # An offer outside the limit is a non-fill, even if the next price would win.
    skipped = execute(cap, 45, 20, 205, lambda _: 100.15, lambda _: 150, lambda _: 150)
    assert skipped.state == "OVER_LIMIT" and skipped.net == 0.0
    # Knowing a close breaches the stop can never fill at that close.
    stopped = execute(cap, 45, 20, 205, lambda _: 100, {45: 10}.get, {45: 99, 46: 9}.get)
    assert stopped.exit_reason == "STOP" and stopped.exit_minute == 46 and stopped.net < -3000
    due = execute(cap, 45, 20, 205, lambda _: 100, {}.get, {64: 150, 65: 101}.get)
    assert due.exit_reason == "TIME" and due.exit_minute == 65
    unknown = execute(cap, 45, 20, 400, lambda _: 100, {}.get, {}.get)
    assert unknown.state == "UNRESOLVED_LOSS_BOUND" and unknown.net == -unknown.debit - 400
    fitted, predicted = ridge(np.array([[1.0, 7], [2.0, 7], [3.0, 7]]), np.array([1.0, 2.0, 3.0]),
                              np.array([[4.0, 9.0]]))
    assert fitted[0] < fitted[-1] < predicted[0] and affordable_for_test()


def affordable_for_test():
    cap = room_price()
    return buy_cost(cap) <= ROOM < buy_cost(cap + 0.05)


def main():
    verify_freeze()
    self_test()
    if OUTPUT.exists() or DETAIL.exists():
        raise RuntimeError("This frozen slate is scored once")
    print("Frozen sources and execution cases verified", flush=True)
    calendar, data_days, features, orders, io, outcomes, parity = build()
    all_days = [d for d in calendar if d[:4] in YEARS]
    actual_days = [d for d in data_days if d[:4] in YEARS]
    # Explicit zeros for non-eligible market sessions, including expiry days.
    for day in set(all_days) - set(actual_days):
        outcomes[day] = {}
    print(f"Usable feature-option days: {len(data_days)}, evaluation {len(actual_days)}/{len(all_days)}", flush=True)
    results = {
        "calendar_sessions": dict(Counter(day[:4] for day in all_days)),
        "evaluation_non_expiry_feature_option_days": dict(Counter(day[:4] for day in actual_days)),
        "feature_option_days": dict(Counter(day[:4] for day in data_days)),
        "ledger10_parity_checks": parity,
        "entry_cap_rupees": ROOM,
        "slots": {},
    }
    slots, daily = results["slots"], {}
    for slot in ("R1", "R2", "R3", "R4"):
        a, b, meta = direction_review(data_days, features, slot)
        slots[slot] = {"forecast": meta, "economics": evaluate(all_days, a, b, outcomes, daily, slot)}
        print(slot, meta.get("predictions"), flush=True)
    raw, robust, adaptive, price_control = direct_policies(data_days, features, orders, io, outcomes)
    slots["R5"] = evaluate(all_days, raw, price_control, outcomes, daily, "R5")
    slots["R6"] = evaluate(all_days, robust, raw, outcomes, daily, "R6")
    slots["R7"] = evaluate(all_days, adaptive, robust, outcomes, daily, "R7")
    slots["R7"]["chosen_horizons"] = dict(Counter(p[1] for p in adaptive.values() if p is not None))
    slots["R8"] = evaluate(all_days, robust, robust, outcomes, daily, "R8", route="value")
    print("R5–R8 scored", flush=True)

    slots["R9"] = quote_review(all_days, robust, features, orders, outcomes)
    print("R9: walked quote checks complete", flush=True)
    slots["R10"] = gold_review(all_days, robust, outcomes)
    print("R10: Gold parity and overlap checks complete", flush=True)

    DETAIL.parent.mkdir(exist_ok=True)
    with DETAIL.open("x", encoding="utf-8") as f:
        json.dump(daily, f, ensure_ascii=False, default=str)
    with OUTPUT.open("x", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, allow_nan=False)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        self_test()
        print("Execution and model mechanics passed")
    else:
        main()
