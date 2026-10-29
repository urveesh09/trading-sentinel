"""O29f year dataset - ICICI Breeze 1-minute candles as a fno_policy_replay dataset (research only).

The quote archive the earlier F&O studies replay starts on Sep 10 2026. ICICI's free Breeze API serves 1-minute candles
of expired NIFTY / SENSEX options and futures, so the same shipped book can be replayed from Jan 2026. A candle is
not a quote, so the dataset declares its model before any strategy is scored on it:

  * one observation per minute, stamped at the minute's last second, priced at the minute's close (the live
    fast-exit loop and the archive both sample about once a minute: median 59 s between archived batches);
  * option bid / ask = close -/+ half the 75th-percentile spread the archive recorded for that premium level
    (NIFTY near strikes, 09:30-15:15, Sep 10 - Oct 28: Rs 0.10 under Rs 50 up to Rs 0.80 under Rs 450);
  * a contract without a trade in a minute keeps its last price and its last trade time (the planner's
    quote-age gate then ages it as live would); day volume is the running sum of the minute volumes;
  * the front future (nearest monthly) carries the underlying price; its 5-minute bars come from its own
    1-minute bars, including the 21 calendar days before it became the front contract (as live reads them);
  * the swing regime (only REGIME_3_CRISIS gates F&O): the label the live engine logged for the bar wherever
    Production logged one (Jul 14 - Oct 28, from the read-only O29b export), else UNKNOWN, which leaves the gate
    open. A rebuild with the live RegimeEngine from daily NIFTY / NIFTY BANK bars (scans at 09:20 and 14:45) is
    kept in the manifest as a description only: before any scoring it called 30 of 32 Sep-Oct sessions a crisis
    where live logged one, so it is not used;
  * lot size: today's contract (NIFTY 65), so every session is sized as the book would size it now.

``export`` copies one underlying out of the download into a sealed, hashed dataset; ``YearData`` reads only that.
No network, no broker, no Production.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pickle
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path[:0] = [str(ROOT / "python-engine"), str(ROOT / "scripts")]
import pandas as pd  # noqa: E402

import fno_policy_replay as replay  # noqa: E402
from fno_models import Contract, ContractQuote  # noqa: E402

DOWNLOAD = Path(os.environ.get("BREEZE_HISTORY_DB", Path.home() / "sentinel-operations/breeze-history-20261029/data/"
                               "breeze-history.sqlite"))
LOCAL = HERE / "_local"
SPREAD_P75 = ((50.0, 0.10), (100.0, 0.20), (150.0, 0.30), (200.0, 0.45), (300.0, 0.60), (450.0, 0.80))
SPREAD_ABOVE_PCT = 0.002
UNDERLYING = {"NIFTY": {"lot": 65, "step": 50, "fut_tick": 0.1}, "SENSEX": {"lot": 20, "step": 100, "fut_tick": 0.05}}
SCAN_TIMES = ("09:20", "14:45")
TICK = 0.05


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def token_for(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def spread_for(premium: float) -> float:
    for below, spread in SPREAD_P75:
        if premium < below:
            return spread
    return max(SPREAD_P75[-1][1], round(SPREAD_ABOVE_PCT * premium / TICK) * TICK)


def bid_ask(close: float) -> tuple[float, float]:
    half = spread_for(close) / 2
    bid = max(TICK, math.floor((close - half) / TICK + 1e-9) * TICK)
    ask = max(bid + TICK, math.ceil((close + half) / TICK - 1e-9) * TICK)
    return round(bid, 2), round(ask, 2)


# ---- export ------------------------------------------------------------------------------------------------------

def _rows(con, sql, args=()):
    return con.execute(sql, args).fetchall()


def rebuild_regimes(daily_nifty: pd.DataFrame, daily_bank: pd.DataFrame, minutes: pd.DataFrame,
                    sessions: list[str]) -> dict:
    """day -> {"prior", "0920", "1445"}: the live RegimeEngine fed at each scan as run_screener feeds it."""
    import numpy as np
    from engine import calc_atr, calc_ema
    from regime import RegimeEngine
    engine = RegimeEngine()
    out, prior = {}, "UNKNOWN"
    for day in sessions:
        d = date.fromisoformat(day)
        # run_screener reads 365 calendar days of NIFTY and 90 of NIFTY BANK, today's candle included
        hist = daily_nifty[(daily_nifty.index.date < d) & (daily_nifty.index.date >= d - timedelta(days=365))]
        bank_hist = daily_bank[(daily_bank.index.date < d) & (daily_bank.index.date >= d - timedelta(days=90))]
        today_min = minutes[minutes.index.date == d]
        row = {"prior": prior}
        for scan in SCAN_TIMES:
            hh, mm = map(int, scan.split(":"))
            part = today_min[(today_min.index.hour * 60 + today_min.index.minute) < hh * 60 + mm]
            if part.empty or len(hist) < 220 or len(bank_hist) < 40:
                row[scan.replace(":", "")] = prior
                continue
            bar = pd.DataFrame({"open": [float(part["open"].iloc[0])], "high": [float(part["high"].max())],
                                "low": [float(part["low"].min())], "close": [float(part["close"].iloc[-1])]},
                               index=[pd.Timestamp(d)])
            nifty_df = pd.concat([hist[["open", "high", "low", "close"]], bar])
            bank_close = pd.concat([bank_hist["close"], pd.Series([float(bank_hist["close"].iloc[-1])],
                                                                  index=[pd.Timestamp(d)])])
            close = nifty_df["close"]
            atr = calc_atr(nifty_df["high"], nifty_df["low"], close)
            log_returns = np.diff(np.log(close.values))
            realized_vol = float(np.std(log_returns[-20:]) * np.sqrt(252)) if len(log_returns) >= 20 else 0.18
            n = min(60, len(nifty_df), len(bank_close))
            nb = [float(close.iloc[-(i + 1)] / bank_close.iloc[-(i + 1)]) for i in range(n)][::-1]
            ema50 = float(calc_ema(50, close).iloc[-1])
            breadth = max(0.30, min(0.70, 0.30 + ((float(close.iloc[-1]) / ema50 if ema50 > 0 else 1.0) - 0.98) * 10))
            state = engine.update_regime(
                nifty_atr_current=float(atr.iloc[-1]), nifty_atr_baseline=float(atr.rolling(200).mean().iloc[-1]),
                realized_vol=realized_vol, nifty_close=float(close.iloc[-1]),
                nifty_ema20=float(calc_ema(20, close).iloc[-1]), banknifty_close=float(bank_close.iloc[-1]),
                nb_ratio_history=nb, breadth=breadth, vix=None, nifty_50=float(close.iloc[-1]))
            prior = state.regime.value
            row[scan.replace(":", "")] = prior
        out[day] = row
    return out


def _frame(rows) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close"])
    frame.index = pd.to_datetime(frame.pop("datetime"))
    return frame[~frame.index.duplicated(keep="last")].sort_index()


def export(underlying: str, first: str, last: str, out: Path) -> None:
    if (out / "manifest.json").exists():
        raise SystemExit(f"{out} already exported; a sealed dataset is never rewritten")
    out.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{DOWNLOAD.resolve().as_posix()}?mode=ro", uri=True)
    dst_path = out / "breeze.sqlite"
    dst = sqlite3.connect(dst_path)
    dst.execute("CREATE TABLE candles (kind TEXT, expiry TEXT, strike REAL, opt TEXT, datetime TEXT, open REAL, "
                "high REAL, low REAL, close REAL, volume REAL, oi REAL, PRIMARY KEY (kind, expiry, strike, opt, datetime))")
    rows = _rows(src, "SELECT kind, expiry, strike, opt, datetime, open, high, low, close, volume, oi FROM candles "
                      "WHERE underlying=? AND interval='1minute' AND kind IN ('index','future','option') "
                      "AND substr(datetime,12,5) >= '09:15' AND substr(datetime,12,5) <= '15:39' ORDER BY 1,2,3,4,5",
                 (underlying,))
    dst.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    dst.commit()
    index_days = sorted({r[4][:10] for r in rows if r[0] == "index"})
    option_expiries = sorted({r[1] for r in rows if r[0] == "option"})
    future_expiries = sorted({r[1] for r in rows if r[0] == "future"})
    fut_days = {}
    for r in rows:
        if r[0] == "future":
            fut_days.setdefault(r[4][:10], set()).add(r[1])
    sessions = []
    for day in index_days:
        if not (first <= day <= last):
            continue
        front = next((e for e in future_expiries if e >= day), None)
        if front and front in fut_days.get(day, set()):
            sessions.append(day)
    weekly = option_expiries  # each option row carries its contract's real expiry date
    daily = {}
    for name in ("NIFTY", "BANKNIFTY"):
        daily[name] = _frame(_rows(src, "SELECT datetime, open, high, low, close FROM candles WHERE kind='daily' "
                                        "AND underlying=? ORDER BY datetime", (name,)))
        daily[name].index = pd.to_datetime(daily[name].index.date)
    index_min = _frame([(r[4], r[5], r[6], r[7], r[8]) for r in rows if r[0] == "index"])
    rebuilt = rebuild_regimes(daily["NIFTY"], daily["BANKNIFTY"], index_min, sessions)
    logged_db = ROOT / "docs/research/fno/2026-10-28-chop-study/_local/dataset/fno-replay.sqlite"
    with sqlite3.connect(f"file:{logged_db.as_posix()}?mode=ro", uri=True) as live:
        logged = {bar_ts: regime for bar_ts, regime in live.execute(
            "SELECT bar_ts, regime FROM fno_signals WHERE regime IS NOT NULL AND regime != '' ORDER BY evaluated_at")}
    dst.close()
    src.close()
    manifest = {"schema": "o29f_breeze_year_dataset_v1", "underlying": underlying, "window": [first, last],
                "sessions": sessions, "option_expiries": option_expiries, "weekly_expiry_calendar": weekly,
                "future_expiries": future_expiries, "lot_size": UNDERLYING[underlying]["lot"],
                "strike_step": UNDERLYING[underlying]["step"], "spread_p75": SPREAD_P75,
                "spread_above_pct": SPREAD_ABOVE_PCT, "scan_times": SCAN_TIMES, "logged_regimes": logged,
                "logged_regimes_source": "docs/research/fno/2026-10-28-chop-study/_local/dataset (fno_signals)",
                "logged_regimes_sha256": sha(logged_db), "rebuilt_regimes_description_only": rebuilt,
                "rows": len(rows), "source_download_sha256": sha(DOWNLOAD),
                "files_sha256": {"breeze.sqlite": sha(dst_path)}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"exported {underlying}: {len(sessions)} sessions {sessions[0]}..{sessions[-1]}, {len(rows)} rows", flush=True)


# ---- the replay dataset ------------------------------------------------------------------------------------------

class YearData:
    """The fno_policy_replay ReplayData interface over a sealed Breeze export (parsed sessions cached)."""

    def __init__(self, root: Path, cache: Path | None = None):
        self.root = Path(root)
        self.manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        self.db = self.root / "breeze.sqlite"
        self.name = self.manifest["underlying"]
        self.lot = int(self.manifest["lot_size"])
        self.cache = Path(cache) if cache else None
        self._weekly = tuple(date.fromisoformat(e) for e in self.manifest["weekly_expiry_calendar"])
        self._futures = [date.fromisoformat(e) for e in self.manifest["future_expiries"]]
        self._tokens: dict[int, date] = {}
        self._frames: dict = {}
        self._regime_days: dict | None = None
        for expiry in self._futures:   # cached sessions skip _observations; futures_frame still resolves tokens
            self.future_contract(expiry)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(f"file:{self.db.resolve().as_posix()}?mode=ro", uri=True)

    @property
    def days(self) -> list[str]:
        return list(self.manifest["sessions"])

    def option_expiries(self):
        return self._weekly, "breeze_calendar"

    def front_expiry(self, day: date) -> date:
        return next(e for e in self._futures if e >= day)

    def future_contract(self, expiry: date) -> Contract:
        token = token_for(self.name, expiry.isoformat(), "FUT")
        self._tokens[token] = expiry
        return Contract(token=token, tradingsymbol=f"{self.name}{expiry:%y%m%d}FUT", name=self.name, expiry=expiry,
                        strike=0.0, instrument_type="FUT", lot_size=self.lot,
                        tick_size=UNDERLYING[self.name]["fut_tick"])

    def option_contract(self, expiry: date, strike: float, opt: str) -> Contract:
        return Contract(token=token_for(self.name, expiry.isoformat(), float(strike), opt),
                        tradingsymbol=f"{self.name}{expiry:%y%m%d}{int(strike)}{opt}", name=self.name, expiry=expiry,
                        strike=float(strike), instrument_type=opt, lot_size=self.lot, tick_size=TICK)

    def observations(self, day: str):
        if self.cache:
            path = self.cache / f"{day}.pkl"
            if path.is_file():
                return pickle.loads(path.read_bytes())
        parsed = self._observations(day)
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)
            part = path.with_name(f"{day}.{os.getpid()}.part")
            part.write_bytes(pickle.dumps(parsed, protocol=pickle.HIGHEST_PROTOCOL))
            os.replace(part, path)
        return parsed

    def _observations(self, day: str):
        d = date.fromisoformat(day)
        front = self.front_expiry(d)
        fut = self.future_contract(front)
        nxt = next((e for e in self._weekly if e >= d), None)
        with self._connect() as con:
            fut_rows = con.execute("SELECT datetime, close, volume FROM candles WHERE kind='future' AND expiry=? "
                                   "AND datetime LIKE ? ORDER BY datetime", (front.isoformat(), f"{day}%")).fetchall()
            opt_rows = con.execute("SELECT datetime, strike, opt, close, volume, oi FROM candles WHERE kind='option' "
                                   "AND expiry=? AND datetime LIKE ? ORDER BY datetime",
                                   (nxt.isoformat() if nxt else "", f"{day}%")).fetchall()
        by_minute: dict[str, list] = {}
        for row in opt_rows:
            by_minute.setdefault(row[0], []).append(row[1:])
        contracts: dict[tuple, Contract] = {}
        state: dict[int, dict] = {}
        notes: Counter = Counter()
        out = []
        fut_volume = 0
        for stamp, close, volume in fut_rows:
            minute = datetime.fromisoformat(stamp)
            at = replay.IST.localize(minute + timedelta(seconds=59))
            fut_volume += int(volume or 0)
            future = ContractQuote(contract=fut, bid=float(close), ask=float(close), ltp=float(close), volume=fut_volume,
                                   last_trade_time=at)
            for strike, opt, o_close, o_volume, oi in by_minute.get(stamp, ()):
                key = (strike, opt)
                if key not in contracts:
                    contracts[key] = self.option_contract(nxt, strike, opt)
                    state[contracts[key].token] = {"volume": 0}
                s = state[contracts[key].token]
                s["volume"] += int(o_volume or 0)
                s["close"], s["oi"] = float(o_close), int(oi or 0)
                if o_volume:
                    s["ltt"] = at
            options = {}
            for key, contract in contracts.items():
                s = state[contract.token]
                if "close" not in s or s["close"] <= 0:
                    continue
                bid, ask = bid_ask(s["close"])
                options[contract.token] = ContractQuote(
                    contract=contract, bid=bid, ask=ask, ltp=s["close"], oi=s["oi"], volume=s["volume"],
                    last_trade_time=s.get("ltt"), bid_quantity=10 * self.lot, ask_quantity=10 * self.lot)
            out.append(replay.Observation(at, future, options))
        if not fut_rows:
            notes["session_without_future"] += 1
        return out, notes

    def futures_frame(self, token: int, day: date) -> pd.DataFrame:
        expiry = self._tokens[token]
        key = (expiry, day)
        if key in self._frames:
            return self._frames[key]
        start = (day - timedelta(days=replay.RVOL_FETCH_CALENDAR_DAYS)).isoformat()
        with self._connect() as con:
            rows = con.execute("SELECT datetime, open, high, low, close, volume FROM candles WHERE kind='future' AND "
                               "expiry=? AND datetime>=? AND datetime<? ORDER BY datetime",
                               (expiry.isoformat(), start, (day + timedelta(days=1)).isoformat())).fetchall()
        frame = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume"])
        frame.index = pd.to_datetime(frame.pop("datetime"))
        bars = frame.resample("5min", label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["open"])
        self._frames = {k: v for k, v in self._frames.items() if k[1] == day}
        self._frames[key] = bars
        return bars

    def regime(self, bar_ts: str, day: str):
        """The live label logged for this bar, else the latest earlier one that day (ReplayData's rule)."""
        logged = self.manifest["logged_regimes"]
        if bar_ts in logged:
            return logged[bar_ts], "logged_for_bar"
        if self._regime_days is None:
            self._regime_days = {}
            for key in sorted(logged):
                self._regime_days.setdefault(key[:10], []).append(key)
        earlier = [k for k in self._regime_days.get(day, ()) if k < bar_ts]
        if earlier:
            return logged[earlier[-1]], "logged_earlier_same_day"
        return "UNKNOWN", "not_logged"

    def live_tick_phase(self, day: str):
        return None

    def paper_closes(self):
        return []


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["export"])
    cli.add_argument("--underlying", default="NIFTY")
    cli.add_argument("--first", default="2026-01-01")
    cli.add_argument("--last", default="2026-10-28")
    cli.add_argument("--out", type=Path, default=LOCAL / "dataset-nifty")
    args = cli.parse_args()
    export(args.underlying, args.first, args.last, args.out)
