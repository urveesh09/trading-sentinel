"""Audit deployed paper premium and compare conditional one-lot trial cash."""
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
from statistics import median
import subprocess
import sys

from anatomy import DATASETS, read, trades

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "python-engine"))
from fno_costs import calc_fno_costs
from fno_live_test import entry_limit


def rounded(value):
    return round(value, 2)


def paper_exposure(rows, days):
    events = defaultdict(Counter)
    for trade in rows:
        assert trade["status"] == "CLOSED" and not trade["adds"]
        premium = trade["initial_entry_premium"] * trade["initial_quantity"]
        intervals = [(trade["initial_entry_time"], trade["exit_time"], premium)]
        intervals.extend((c["at"], c["exit_at"], c["ask"] * c["qty"]) for c in trade["n10_children"])
        for opened, closed, paid in intervals:
            start, end = datetime.fromisoformat(opened), datetime.fromisoformat(closed)
            assert start.date() == end.date() and start < end and paid > 0
            events[opened[:10]][start] += paid
            events[opened[:10]][end] -= paid
    assert set(events) <= set(days)
    duration, active, weighted = 0., 0., 0.
    peaks = []
    for day in days:
        points = events[day]
        sample = next(iter(points), None)
        tz = sample.tzinfo if sample else None
        opening = datetime.fromisoformat(day + "T09:15:00").replace(tzinfo=tz)
        last = datetime.fromisoformat(day + "T15:10:00").replace(tzinfo=tz)
        duration += (last - opening).total_seconds()
        prev, invested, peak = opening, 0., 0.
        for at, change in sorted(points.items()):
            span = (min(at, last) - min(prev, last)).total_seconds()
            assert span >= 0
            if invested > 0:
                active += span
                weighted += invested * span
            invested += change
            assert invested >= -1e-6
            peak = max(peak, invested)
            prev = at
        assert abs(invested) < 1e-6
        if peak:
            peaks.append(peak)
    return {"regular_sessions": len(days), "active_days": len(peaks),
            "peak_open_premium": rounded(max([0., *peaks])),
            "median_active_day_peak": rounded(median(peaks)) if peaks else 0.,
            "peak_share_of_opening_cash_pct": rounded(100 * max([0., *peaks]) / 250000.),
            "peak_share_of_nominal_premium_cap_pct": rounded(100 * max([0., *peaks]) / 37500.),
            "market_clock_with_exposure_pct": rounded(100 * active / duration),
            "time_weighted_open_premium": rounded(weighted / duration),
            "time_weighted_open_premium_if_active": rounded(weighted / active) if active else 0.}


def mirror(rows, starting, lot, adverse):
    equity = peak = low = float(starting)
    drawdown = 0.
    closed, decisions = [], []
    counts, daily = Counter(), Counter()
    position = None
    rejects = Counter()

    def settle():
        nonlocal equity, peak, low, drawdown, position
        equity += position["net"]
        peak = max(equity, peak)
        low = min(equity, low)
        drawdown = max(drawdown, (peak - equity) / peak)
        daily[position["exit_at"][:10]] += position["net"]
        closed.append(position)
        position = None

    for trade in sorted(rows, key=lambda t: t["initial_entry_time"]):
        stamp = trade["initial_entry_time"]
        day = stamp[:10]
        if position and position["exit_at"] <= stamp:
            settle()
        ask = trade["initial_entry_premium"]
        observed = ask * (1.01 if adverse else 1.)
        limit = entry_limit(observed, .05, 2, ask * 1.02)
        reserve = (limit * lot + calc_fno_costs(limit, 0., lot)) if limit is not None else None
        if position:
            reason = "position_open"
        elif counts[day] >= 3:
            reason = "day_count"
        elif equity < 7000.:
            reason = "floor"
        elif limit is None:
            reason = "chase"
        elif reserve > equity or limit * lot > starting:
            reason = "cash"
        else:
            reason = "admitted"
        decisions.append({"at": stamp, "symbol": trade["tradingsymbol"], "reason": reason,
                          "limit": limit, "reserve": reserve, "equity": equity})
        if reason != "admitted":
            rejects[reason] += 1
            continue
        entry = limit if adverse else ask
        exit_ = trade["exit_premium"] * (.99 if adverse else 1.)
        gross = (exit_ - entry) * lot
        fees = calc_fno_costs(entry, exit_, lot)
        stress = 205. if adverse else 0.
        position = {"entry_at": stamp, "symbol": trade["tradingsymbol"], "exit_at": trade["exit_time"],
                    "entry": entry, "exit": exit_, "quantity": lot, "reserve": reserve,
                    "gross": gross, "fees": fees, "extra": stress, "net": gross - fees - stress}
        counts[day] += 1
    if position:
        settle()
    assert len(rows) == len(closed) + sum(rejects.values())
    assert abs(sum(daily.values()) - (equity - starting)) < 1e-6
    return {"start": starting, "end": rounded(equity), "low_equity": rounded(low),
            "net": rounded(equity - starting), "closed_drawdown_pct": rounded(drawdown * 100),
            "closed": len(closed), "wins": sum(t["net"] > 0 for t in closed),
            "worst_day": rounded(min([0., *daily.values()])),
            "worst_trade": rounded(min([0., *(t["net"] for t in closed)])),
            "best_day": rounded(max([0., *daily.values()])),
            "rejects": dict(rejects), "trades": closed, "decisions": decisions}


def main():
    freeze = HERE / "capital-freeze.json"
    spec = read(freeze)
    path = freeze.relative_to(ROOT).as_posix()
    assert spec == json.loads(subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=ROOT))
    for name, expected in spec["files"].items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == expected
    controls = read(HERE / "round1-freeze.json")
    result = {}
    for year, root in DATASETS.items():
        manifest_file = root / "manifest.json"
        assert hashlib.sha256(manifest_file.read_bytes()).hexdigest() == controls["data_manifest_sha256"][year]
        src, raw = trades(year, "N11T")
        assert hashlib.sha256(src.read_bytes()).hexdigest() == controls["controls_sha256"][year]["N11T"]
        manifest = read(manifest_file)
        lot = int(manifest["lot_size"])
        days = [d for d in manifest["sessions"] if raw["window"][0] <= d <= raw["window"][1]
                and d not in manifest["weekly_expiry_calendar"]]
        rows = raw["trades"]
        paper = paper_exposure(rows, days)
        accounts = {f"{start}-{label}": mirror(rows, start, lot, adverse)
                    for start in (12500, 15000) for label, adverse in (("standard", False), ("adverse", True))}
        result[year] = {"lot": lot, "paper": paper, "trial": accounts}
        print(year, paper, {k: (v["closed"], v["net"], v["worst_day"], v["rejects"])
                            for k, v in accounts.items()}, flush=True)
    with (HERE / "_local/capital-detail.json").open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    for year in result.values():
        for account in year["trial"].values():
            account.pop("trades")
            account.pop("decisions")
    with (HERE / "capital-results.json").open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
