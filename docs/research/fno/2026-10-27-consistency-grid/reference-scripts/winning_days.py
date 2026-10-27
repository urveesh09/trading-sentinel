"""Descriptive (selection window A only): what did the O27 grid's winning entries have in common at entry time?

Every distinct entry (day, entry time, direction) any of the 360 arms took on Sep 10 - Oct 9, its median net across
the arms that took it, and causal features measured on the closed 5-minute futures bars before the entry."""
import json
import pickle
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, r"C:\Users\Urveesh\Desktop\trading-sentinel\python-engine")
from fno_policy_replay import ReplayData  # noqa: E402
from fno_shadow import _prior_sessions  # noqa: E402
from fno_engine_mom import SESSION_OPEN_MIN, _minutes_ist  # noqa: E402

STUDY = Path(r"C:\Users\Urveesh\Desktop\trading-sentinel\docs\research\fno\2026-10-27-consistency-grid")
DATA = ReplayData(STUDY / "_local" / "dataset")
CACHE = next((STUDY / "_local" / "observations").iterdir())
A = ("2026-09-10", "2026-10-09")

entries = defaultdict(list)
for f in (STUDY / "_local" / "arms").glob("*.json"):
    if f.stem.startswith("PARITY"):
        continue
    for t in json.loads(f.read_text(encoding="utf-8"))["trades"]:
        day = t["entry_time"][:10]
        if A[0] <= day <= A[1] and "net_pnl" in t:
            entries[(day, t["entry_time"][:16], t["direction"])].append((t["net_pnl"], f.stem.split("__")[0]))

frames = {}
rows = []
for (day, at, direction), nets in sorted(entries.items()):
    if day not in frames:
        obs, _ = pickle.loads((CACHE / f"{day}.pkl").read_bytes())
        frames[day] = DATA.futures_frame(obs[0].future.contract.token, datetime.fromisoformat(day).date())
    frame = frames[day]
    now = datetime.fromisoformat(at)
    closed = frame[frame.index + timedelta(minutes=5) <= now]
    today = closed[[d == now.date() for d in closed.index.date]]
    long = direction == "LONG"
    sign = 1 if long else -1
    history = _prior_sessions(closed, now.date(), 30)
    day_open = float(today["open"].iloc[0])
    close = float(today["close"].iloc[-1])
    vol = today["volume"].astype(float)
    vwap = float((((today["high"] + today["low"] + today["close"]) / 3) * vol).sum() / vol.sum()) if vol.sum() else close
    or30 = today[[SESSION_OPEN_MIN <= _minutes_ist(s) < SESSION_OPEN_MIN + 30 for s in today.index]]
    widths = [r["or_width"] for r in history[-10:] if r["or_width"]]
    gap = (day_open - history[-1]["close"]) / history[-1]["close"] if history else 0.0
    ranges = [r["high"] - r["low"] for r in history[-4:]]
    rest = closed[closed.index > now]  # (empty: closed bars only) - outcome comes from the replay, not from here
    rows.append({
        "day": day, "at": at[11:16], "dir": direction, "n_arms": len(nets),
        "net_median": statistics.median(n for n, _ in nets),
        "gap_with": "with gap" if abs(gap) >= 0.001 and gap * sign > 0 else ("against gap" if abs(gap) >= 0.001 else "flat open"),
        "vwap": "VWAP side ok" if (close - vwap) * sign > 0 else "VWAP against",
        "or_bias": "range bias with" if (float(or30["close"].iloc[-1]) - day_open) * sign > 0 else "range bias against",
        "or_width": ("narrow range" if widths and (or30["high"].max() - or30["low"].min()) <= sum(widths) / len(widths)
                     else "wide range"),
        "nr4": "prior day NR4" if len(ranges) == 4 and ranges[-1] <= min(ranges) else "prior day normal",
        "time": "before 10:30" if now.hour * 60 + now.minute < 630 else ("10:30-12:00" if now.hour < 12 else "after 12:00"),
    })

print(f"{len(rows)} distinct entries on A (Sep 10 - Oct 9); winners = median net across arms > 0")
for feature in ("gap_with", "vwap", "or_bias", "or_width", "nr4", "time"):
    groups = defaultdict(list)
    for r in rows:
        groups[r[feature]].append(r["net_median"])
    for value, nets in sorted(groups.items()):
        print(f"  {feature:9} {value:20} n={len(nets):3}  win {sum(x > 0 for x in nets) / len(nets):4.0%}  "
              f"median {statistics.median(nets):7.0f}  total {sum(nets):8.0f}")
print("\nentries (day, time, dir, arms, median net, features):")
for r in sorted(rows, key=lambda r: -r["net_median"]):
    print(f"  {r['day']} {r['at']} {r['dir']:5} arms={r['n_arms']:3} {r['net_median']:7.0f}  {r['gap_with']:11} {r['vwap']:13} "
          f"{r['or_bias']:18} {r['or_width']:12} {r['nr4']:16} {r['time']}")
