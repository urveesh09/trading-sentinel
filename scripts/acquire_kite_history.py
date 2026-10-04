"""Download Kite historical candles into a research snapshot (read-only market data).

Yahoo keeps only ~60 days of 15-minute and ~30 days of 1-minute bars, so every
recent intraday day has already been used by a study. Kite's historical API
serves older months, which is where untouched intraday windows come from.

    python scripts/acquire_kite_history.py --tickers-from <report/freeze.json or .txt> \
        --start 2026-01-01 --end 2026-07-31 --interval 15minute --history-days 900 \
        --index "NIFTY 50" --out docs/research/kite/<dated>/_local/validated-kite.sqlite

Credentials: ZERODHA_API_KEY (environment or repo .env) and a same-day access
token from KITE_ACCESS_TOKEN or ``--token-file`` (the engine's
``kite_token.json``; read only). KITE_BASE_URL may point at the relay.
The output is the standard ``sentinel_backtest_snapshot_v1`` (intraday_cache +
ohlcv_cache + manifest) that ``scripts/run_preregistered_study.py`` verifies.
Raw provider responses are kept under ``raw/`` beside the snapshot.

Read the coverage summary only. Do not look at strategy results for a window
you intend to keep untouched.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta
import io
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-engine"))

# Kite limits per request (days) by interval, and its historical rate limit.
MAX_DAYS = {"minute": 60, "15minute": 200, "day": 2000}
REQUEST_GAP_SEC = 0.36


def _env_value(name: str) -> str:
    if os.getenv(name):
        return os.environ[name]
    for env in (ROOT / "python-engine" / ".env", ROOT / ".env"):
        if env.is_file():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith(f"{name}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _token(path: str | None) -> str:
    if os.getenv("KITE_ACCESS_TOKEN"):
        return os.environ["KITE_ACCESS_TOKEN"]
    if not path:
        raise SystemExit("provide KITE_ACCESS_TOKEN or --token-file")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    token = payload.get("access_token") or payload.get("token")
    if not token:
        raise SystemExit("token file has no access_token")
    return token


class Kite:
    def __init__(self, api_key: str, token: str, base_url: str, raw_dir: Path):
        self.headers = {"X-Kite-Version": "3", "Authorization": f"token {api_key}:{token}",
                        "User-Agent": "TradingSentinelResearch/1.0"}
        self.base, self.raw_dir, self.last = base_url.rstrip("/"), raw_dir, 0.0
        raw_dir.mkdir(parents=True, exist_ok=True)

    def _get(self, path: str) -> bytes:
        wait = REQUEST_GAP_SEC - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            self.last = time.monotonic()
            try:
                with urlopen(Request(self.base + path, headers=self.headers), timeout=30) as response:
                    return response.read()
            except HTTPError as exc:
                if exc.code == 429 and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                body = exc.read()[:300].decode("utf-8", "replace")
                raise SystemExit(f"Kite HTTP {exc.code} for {path.split('?')[0]}: {body}") from None
        raise SystemExit("Kite rate limit persisted")

    def instruments(self) -> dict[str, int]:
        rows = csv.DictReader(io.StringIO(self._get("/instruments/NSE").decode("utf-8")))
        return {row["tradingsymbol"].upper(): int(row["instrument_token"]) for row in rows}

    def candles(self, token: int, interval: str, start: date, end: date, label: str) -> list[list]:
        out, first = [], start
        while first <= end:
            last = min(first + timedelta(days=MAX_DAYS[interval] - 1), end)
            query = urlencode({"from": f"{first} 09:00:00", "to": f"{last} 15:30:00"})
            raw = self._get(f"/instruments/historical/{token}/{interval}?{query}")
            (self.raw_dir / f"{quote(label, safe='')}_{interval}_{first}_{last}.json").write_bytes(raw)
            payload = json.loads(raw)
            if payload.get("status") != "success":
                raise SystemExit(f"Kite error for {label}: {payload.get('message')}")
            out.extend(payload["data"]["candles"])
            first = last + timedelta(days=1)
        return out


def _iso(stamp: str) -> str:
    """Kite '2026-01-01T09:15:00+0530' -> '2026-01-01T09:15:00+05:30' (Yahoo snapshot format)."""
    parsed = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S%z")
    return parsed.isoformat()


def _tickers(source: str) -> list[str]:
    path = Path(source)
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        # A study's traded universe first (freeze config / report request), then a snapshot's request.
        for keys in (("config", "tickers"), ("request", "config", "tickers"),
                     ("bound", "snapshot", "request", "tickers")):
            node = data
            for key in keys:
                node = node.get(key) if isinstance(node, dict) else None
            if isinstance(node, list) and node:
                return [str(t).upper() for t in node]
        raise SystemExit(f"no ticker list in {source}")
    return [line.strip().upper() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def acquire(args) -> dict:
    from backtest_cli import write_snapshot
    out = Path(args.out).resolve()
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    api_key = _env_value("ZERODHA_API_KEY")
    if not api_key:
        raise SystemExit("ZERODHA_API_KEY missing")
    kite = Kite(api_key, _token(args.token_file), args.base_url or _env_value("KITE_BASE_URL") or "https://api.kite.trade",
                out.parent / "raw")
    tokens = kite.instruments()
    names = _tickers(args.tickers_from)
    wanted = [*names, *([args.index.upper()] if args.index else [])]
    intraday, daily, coverage = [], [], {"missing_instrument": [], "empty": [], "tickers": {}}
    history_start = start - timedelta(days=args.history_days)
    for count, name in enumerate(wanted, 1):
        token = tokens.get(name)
        if token is None:
            coverage["missing_instrument"].append(name)
            continue
        bars = kite.candles(token, args.interval, start, end, name)
        days = kite.candles(token, "day", history_start, end, name)
        if not bars:
            coverage["empty"].append(name)
        for stamp, o, h, low, c, v, *_ in bars:
            intraday.append([name, args.interval, _iso(stamp), o, h, low, c, v])
        for stamp, o, h, low, c, v, *_ in days:
            daily.append([name, stamp[:10], o, h, low, c, v])
        coverage["tickers"][name] = {"bars": len(bars), "daily": len(days)}
        if count % 25 == 0:
            print(f"{count}/{len(wanted)} instruments", flush=True)
    request = {"provider": "KITE_HISTORICAL_API", "start": args.start, "end": args.end, "interval": args.interval,
               "history_days": args.history_days, "history_start": history_start.isoformat(),
               "tickers": names, "index": args.index or None}
    manifest = write_snapshot({"intraday": intraday, "daily": daily, "request": request}, str(out),
                              source="kite_historical_api (read-only market data)")
    (out.parent / "coverage.json").write_text(json.dumps(coverage, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"rows": manifest["row_counts"], "missing_instrument": len(coverage["missing_instrument"]),
                      "empty": len(coverage["empty"]), "snapshot": str(out)}, indent=2))
    return manifest


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("--tickers-from", required=True)
    cli.add_argument("--start", required=True)
    cli.add_argument("--end", required=True)
    cli.add_argument("--interval", choices=("minute", "15minute"), default="15minute")
    cli.add_argument("--history-days", type=int, default=900)
    cli.add_argument("--index", default="NIFTY 50", help="index tradingsymbol to include ('' for none)")
    cli.add_argument("--token-file")
    cli.add_argument("--base-url")
    cli.add_argument("--out", required=True)
    acquire(cli.parse_args())


if __name__ == "__main__":
    main()
