"""Descriptive loss-day research, no new strategy, fit, API or Production access.

Original study books and annual fresh starts are preserved. Comparisons are
exploratory and conditional on a traded day, not calibrated future forecasts.
"""
import hashlib
import json
import math
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
FNO = ROOT / "docs/research/fno"
DATA = {"2025": FNO / "2026-10-30-nifty-2025-test/_local/dataset-nifty-2025",
        "2026": FNO / "2026-10-29-year-genome/_local/dataset-nifty"}
SIDES = ("open_drive", "or_width", "gap", "nr", "trend5", "adx14", "rv20", "ret20_abs",
         "prev_range_rel", "prev_body", "trend_regime", "dmi_dir", "ema_dir")


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def sha(p):
    return hashlib.file_digest(p.open("rb"), "sha256").hexdigest()


def norm(t, field="net_pnl"):
    return float(t[field]) / max(1, int(t.get("lots_at_exit") or 1))


def summarise(rows):
    losses = [r for r in rows if r["net"] < -.005]
    wins = [r for r in rows if r["net"] > .005]
    return {"days": len(rows), "active": sum(r["trades"] > 0 for r in rows),
            "losing_days": len(losses), "winning_days": len(wins),
            "flat_active_days": sum(r["trades"] > 0 and abs(r["net"]) <= .005 for r in rows),
            "no_trade_days": sum(r["trades"] == 0 for r in rows),
            "loss_rate_active": round(len(losses) / sum(r["trades"] > 0 for r in rows), 3)
            if any(r["trades"] for r in rows) else None,
            "net": round(sum(r["net"] for r in rows)),
            "loss_days_net": round(sum(r["net"] for r in losses)),
            "win_days_net": round(sum(r["net"] for r in wins)),
            "median_loss": round(statistics.median(r["net"] for r in losses)) if losses else None,
            "median_win": round(statistics.median(r["net"] for r in wins)) if wins else None}


def bucket_comparison(rows, key):
    groups = defaultdict(list)
    for r in rows:
        if r["trades"]:
            groups[str(r.get(key))].append(r)
    return {k: summarise(v) for k, v in sorted(groups.items())}


def entry_metrics(frame, entry):
    """Use completed five-minute bars only; no later bar affects a result."""
    five = frame.resample("5min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    five = five[five.index + pd.Timedelta(minutes=5) <= entry]
    if five.empty or five.index[0].hour * 60 + five.index[0].minute != 555:
        return {"er6": None, "crosses6": None, "stretch_or": None}
    typical = (five.high + five.low + five.close) / 3
    volume = five.volume
    if (volume < 0).any() or volume.sum() <= 0:
        vw = None
    else:
        vw = (typical * volume).cumsum() / volume.cumsum().replace(0, math.nan)
    er = None
    if len(five) >= 7:
        c = five.close.iloc[-7:]
        path = c.diff().abs().sum()
        er = abs(float(c.iloc[-1] - c.iloc[0])) / float(path) if path > 0 else 0.
    crosses = None
    if vw is not None and len(five) >= 7:
        signs = (five.close - vw).iloc[-7:]
        # Exact touches do not count as a cross, and do not erase a prior side.
        signs = signs.apply(lambda v: 1 if v > 0 else -1 if v < 0 else math.nan).ffill().dropna()
        crosses = int((signs.diff().abs() == 2).sum())
    opening = five[five.index.hour * 60 + five.index.minute < 585]
    width = float(opening.high.max() - opening.low.min()) if len(opening) == 6 else 0.
    stretch = abs(float(five.close.iloc[-1] - vw.iloc[-1])) / width if vw is not None and width > 0 else None
    return {"er6": er, "crosses6": crosses, "stretch_or": stretch}


def describe_trades(ts):
    closed = [t for t in ts if t.get("net_pnl") is not None]
    def by(key):
        groups = defaultdict(list)
        for t in closed:
            groups[str(t.get(key))].append(t)
        return {k: {"trades": len(v), "losses": sum(norm(t) < 0 for t in v),
                    "net": round(sum(norm(t) for t in v))} for k, v in sorted(groups.items())}
    losses = [t for t in closed if norm(t) < 0]
    gross_positive_losses = [t for t in losses if norm(t, "gross_pnl") > 0]
    sign_known = [t for t in losses if t.get("underlying_signed_exit") is not None]
    return {"trades": len(closed), "losing_trades": len(losses), "by_exit": by("exit_reason"),
            "by_direction": by("direction"), "by_member": by("component"), "by_entry_hour": by("entry_hour"),
            "by_dte": by("dte"), "by_entry_efficiency": by("entry_er_bucket"),
            "by_entry_crossings": by("entry_chop"), "by_entry_stretch": by("entry_stretch"),
            "by_daily_direction": by("with_daily_trend"),
            "gross_positive_but_net_negative": len(gross_positive_losses),
            "losing_trade_gross": round(sum(norm(t, "gross_pnl") for t in losses)),
            "losing_trade_costs": round(sum(norm(t, "gross_pnl") - norm(t) for t in losses)),
            "underlying_favorable_at_exit_losses": sum(t["underlying_signed_exit"] > 0 for t in sign_known),
            "underlying_exit_known_losses": len(sign_known),
            "had_favorable_half_open_range_before_exit": sum(t.get("mfe_or", 0) >= .5 for t in losses),
            "favorable_half_open_range_after_losing_exit": sum(t.get("after_exit_mfe_or", 0) >= .5 for t in losses),
            "last_two_excursions_are_hindsight_only": True}


def family(name):
    if name.startswith("NULL"):
        return "RANDOM"
    p = name.split("|")
    return p[1] if len(p) > 1 else name


def main():
    HERE.joinpath("_local").mkdir(exist_ok=True)
    out, hashes = {}, {}
    for year, data in DATA.items():
        manifest = load(data / "manifest.json")
        hashes[year] = {"manifest": sha(data / "manifest.json"),
                        "database_matches_manifest": sha(data / "breeze.sqlite") == manifest["files_sha256"]["breeze.sqlite"]}
        assert hashes[year]["database_matches_manifest"]
        con = sqlite3.connect(f"file:{(data / 'breeze.sqlite').as_posix()}?mode=ro", uri=True)
        dates = [s for s in manifest["sessions"] if s.startswith(year)]
        table_path = FNO / f"2026-10-30-case-study/_local/table-{year}.json"
        table = load(table_path)
        hashes[year]["day_table"] = sha(table_path)
        raw_path = FNO / f"2026-10-30-micro-adaptation/_local/results-raw-{year}.json"
        raw = load(raw_path)
        hashes[year]["trades"] = sha(raw_path)
        bad = {r[0] for r in con.execute("SELECT DISTINCT substr(datetime,1,10) FROM candles WHERE volume<0")}
        short = {r[0] for r in con.execute("SELECT substr(datetime,1,10) FROM candles WHERE kind='index' GROUP BY 1 HAVING COUNT(*)<300")}
        frames = {}
        for day in dates:
            e = next((x for x in manifest["future_expiries"] if x >= day), None)
            rows = con.execute("SELECT datetime,open,high,low,close,volume FROM candles WHERE kind='future' AND expiry=? "
                               "AND datetime>=? AND datetime<? ORDER BY datetime", (e, day, day + "Z")).fetchall()
            f = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume"])
            f.index = pd.to_datetime(f.pop("datetime"))
            frames[day] = f
        con.close()
        books, detailed = {}, {}
        for name in ("REF|LIVE", "REF|TPB", "REF|BEST"):
            trades = [dict(t) for t in raw["trades"][raw["books"][name]] if t.get("net_pnl") is not None]
            by_day = defaultdict(list)
            for t in trades:
                day = t["entry_time"][:10]
                f = frames[day]
                at = pd.Timestamp(t["entry_time"]).tz_localize(None)
                xt = pd.Timestamp(t["exit_time"]).tz_localize(None)
                metrics = entry_metrics(f, at)
                t.update(entry_hour=at.hour,
                         component="TPB" if name == "REF|TPB" else ("SHIPPED", "OR20", "EFF", "TPB")[t["member"]],
                         dte=(date.fromisoformat(next(x for x in manifest["weekly_expiry_calendar"] if x >= day))
                              - date.fromisoformat(day)).days,
                         entry_er_bucket="MISSING" if metrics["er6"] is None else "LOW" if metrics["er6"] < .25
                         else "HIGH" if metrics["er6"] >= .5 else "MID",
                         entry_chop="MISSING" if metrics["crosses6"] is None else "2+" if metrics["crosses6"] >= 2 else "0-1",
                         entry_stretch="MISSING" if metrics["stretch_or"] is None else "STRETCHED" if metrics["stretch_or"] >= .5 else "NEAR")
                trend = (table.get(day, {}).get("side") or {}).get("dmi_dir")
                t["with_daily_trend"] = "UNKNOWN" if trend is None else str(trend == ("UP" if t["direction"] == "LONG" else "DOWN"))
                entry_seen, exit_seen = f[f.index + pd.Timedelta(seconds=59) <= at], f[f.index + pd.Timedelta(seconds=59) <= xt]
                t["underlying_signed_exit"] = None
                if not entry_seen.empty and not exit_seen.empty:
                    direction = 1 if t["direction"] == "LONG" else -1
                    base = float(entry_seen.close.iloc[-1])
                    t["underlying_signed_exit"] = direction * (float(exit_seen.close.iloc[-1]) - base)
                    opening = f[f.index.hour * 60 + f.index.minute < 585]
                    width = float(opening.high.max() - opening.low.min()) if len(opening) == 30 else 0.
                    held = f[(f.index > at.floor("min")) & (f.index <= xt.floor("min"))]
                    later = f[(f.index > xt.floor("min")) & (f.index.hour * 60 + f.index.minute < 910)]
                    for key, segment in (("mfe_or", held), ("after_exit_mfe_or", later)):
                        if width > 0 and not segment.empty:
                            t[key] = max(0., float(segment.high.max()) - base if direction > 0
                                         else base - float(segment.low.min())) / width
                by_day[day].append(t)
            rows = []
            for day in dates:
                ts = by_day[day]
                saved = table.get(day) or {}
                feats, sides = saved.get("features") or {}, saved.get("side") or {}
                f = frames[day]
                efficiency = None
                if len(f) >= 300:
                    path = f.close.diff().abs().sum()
                    efficiency = abs(float(f.close.iloc[-1] - f.close.iloc[0])) / float(path) if path > 0 else 0.
                row = {"date": day, "trades": len(ts), "net": sum(norm(t) for t in ts),
                       "quality_flag": day in bad or day in short,
                       "h_trend_day": feats.get("h_trend_day"),
                       "h_small_range": None if feats.get("h_range_rel") is None else feats["h_range_rel"] < .75,
                       "h_full_day_er": efficiency,
                       "h_reversing_day": None if efficiency is None else efficiency < .05}
                row.update({k: sides.get(k) for k in SIDES})
                rows.append(row)
            assert sum(r["trades"] for r in rows) == len(trades)
            assert abs(sum(r["net"] for r in rows) - sum(norm(t) for t in trades)) < 1e-6
            summary = summarise(rows)
            assert summary["losing_days"] + summary["winning_days"] + summary["flat_active_days"] + summary["no_trade_days"] == len(rows)
            if name == "REF|LIVE":
                assert summary["net"] == {"2025": 271, "2026": 80912}[year]
            clean = [r for r in rows if not r["quality_flag"]]
            books[name] = {"summary": summary, "quality_sensitive_summary": summarise(clean),
                           "halves": {h: summarise([r for r in rows if start <= r["date"] <= end])
                                      for h, start, end in (("H1", year + "-01-01", year + ("-06-30" if year == "2025" else "-05-31")),
                                                             ("H2", year + ("-07-01" if year == "2025" else "-06-01"), year + "-12-31"))},
                           "day_splits": {k: bucket_comparison(rows, k) for k in (*SIDES, "h_trend_day", "h_small_range", "h_reversing_day")},
                           "trade_mechanisms": describe_trades(trades),
                           "trade_mechanisms_quality_sensitive": describe_trades([t for t in trades if t["entry_time"][:10] not in bad | short]),
                           "worst_days": sorted(rows, key=lambda r: r["net"])[:10]}
            detailed[name] = {"days": rows, "trades": trades}
        live_days = detailed["REF|LIVE"]["days"]
        labels = {r["date"]: "LOSS" if r["net"] < -.005 else "WIN" if r["net"] > .005 else "FLAT" for r in live_days}
        library_path = FNO / f"2026-10-30-day-router/_local/results-raw-library-{year}.json"
        library = load(library_path)
        overlaps = defaultdict(list)
        for name, key in library["books"].items():
            ts = [t for t in library["trades"][key] if t.get("net_pnl") is not None]
            daily = defaultdict(float)
            for t in ts:
                daily[t["entry_time"][:10]] += norm(t)
            row = {}
            for label in ("LOSS", "WIN", "FLAT"):
                sample = [daily[d] for d, v in labels.items() if v == label]
                row[label] = {"live_days": len(sample), "candidate_positive_days": sum(v > .005 for v in sample),
                              "candidate_negative_days": sum(v < -.005 for v in sample), "net": round(sum(sample))}
            overlaps[family(name)].append(row)
        families = {fam: {"variants": len(rs), "live_loss_days_median_net": statistics.median(r["LOSS"]["net"] for r in rs),
                          "live_win_days_median_net": statistics.median(r["WIN"]["net"] for r in rs),
                          "median_positive_live_loss_days": statistics.median(r["LOSS"]["candidate_positive_days"] for r in rs),
                          "positive_variants_on_live_loss_days": sum(r["LOSS"]["net"] > 0 for r in rs)}
                    for fam, rs in overlaps.items()}
        out[year] = {"books": books, "quality_dates": sorted((bad | short) & set(dates)),
                     "family_overlap_HINDSIGHT_ONLY": families}
        (HERE / f"_local/details-{year}.json").write_text(json.dumps(detailed, indent=1, allow_nan=False), encoding="utf-8")
    result = {"scope": "descriptive historical research, not Production realised P&L or a predictive strategy test",
              "sources": hashes, "years": out, "quality": "PROVISIONAL", "no_2024_access": True,
              "no_new_replay_or_trading_change": True}
    (HERE / "diagnosis.json").write_text(json.dumps(result, indent=1, allow_nan=False), encoding="utf-8")
    for y, value in out.items():
        print(y, "LIVE", value["books"]["REF|LIVE"]["summary"])
        print(y, "TPB", value["books"]["REF|TPB"]["summary"])
        print(y, "LIVE trade mechanisms", value["books"]["REF|LIVE"]["trade_mechanisms"])


if __name__ == "__main__":
    main()
