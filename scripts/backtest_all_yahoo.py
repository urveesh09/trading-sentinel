"""Yahoo-only non-F&O research: inclusive dates, shipped functions, honest scopes.

python scripts/backtest_all_yahoo.py --start 2026-07-01 --end 2026-09-30
python scripts/backtest_all_yahoo.py --start 2026-09-24 --end 2026-09-30 --tickers PCJEWELLER,SOUTHBANK,RELIANCE

No broker, Production cache, trade history, strategy tuning or qualification.
Yahoo chart responses are archived; interval/identity/clock errors are not repaired.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
import copy
from datetime import date, datetime, time as day_time, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-engine"))
from backtest_cli import _atomic_json_new, policy_manifest, verify_snapshot, write_snapshot
from backtest_lab import BacktestRequest, BacktestUnavailable, STRATEGY_REGISTRY

IST = timezone(timedelta(hours=5, minutes=30))
SOURCE = "YAHOO_FINANCE_CHART_ONLY"
ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/"
MODULES = {
    "penny-mis": "penny_breakout_mis_lifecycle_1m",
    "penny-cnc": "penny_cnc_connors_lifecycle_1d",
    "penny-joint": "penny_joint_lifecycle_portfolio",
    "edge": "penny_edge_daily_evaluator",
    "swing": "swing_regime_daily_evaluator",
    "momentum": "momentum_intraday_15m_replay",
    "range": "range_reversion_daily_evaluator",
    "partner": None,
}
INTRADAY = {"penny-mis": "1m", "penny-cnc": "1m", "penny-joint": "1m", "momentum": "15m"}
CONTEXT = {"NIFTY 50": "^NSEI", "NIFTY BANK": "^NSEBANK", "NIFTYBEES": "NIFTYBEES.NS"}


class YahooDataError(RuntimeError):
    pass


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def iso_day(text: str) -> date:
    day = date.fromisoformat(text)
    if day.isoformat() != text:
        raise ValueError("dates must be YYYY-MM-DD")
    return day


def names(text: str) -> list[str]:
    return sorted({value.strip().upper() for value in text.split(",") if value.strip()})


def read_universe(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("tickers", data) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError(f"expected tickers list: {path}")
    return sorted({str(row["symbol"] if isinstance(row, dict) else row).strip().upper() for row in rows})


def yahoo_symbol(symbol: str, overrides: dict) -> str:
    mapped = str(overrides.get(symbol, CONTEXT.get(symbol, symbol + ".NS"))).upper()
    if not mapped.endswith(".NS") and mapped not in CONTEXT.values():
        raise ValueError(f"only NSE cash/index mappings are allowed: {symbol} -> {mapped}")
    return mapped


def chunks(start: str, end: str, interval: str) -> list[tuple[str, str]]:
    first, last = iso_day(start), iso_day(end)
    if interval != "1m":
        return [(start, end)]
    result = []
    while first <= last:
        stop = min(first + timedelta(days=6), last)
        result.append((first.isoformat(), stop.isoformat()))
        first = stop + timedelta(days=1)
    return result


def parse_chart(payload: dict, symbol: str, mapped: str, interval: str,
                start: str, end: str) -> tuple[list[list], dict]:
    """Preserve invalid price cells as None for B1; do not silently repair rows."""
    chart = payload.get("chart") or {}
    if chart.get("error"):
        error = chart["error"]
        raise YahooDataError(f"{error.get('code')}: {error.get('description')}")
    results = chart.get("result") or []
    if len(results) != 1:
        raise YahooDataError("no unique Yahoo chart result")
    result, first, last = results[0], iso_day(start), iso_day(end)
    meta = result.get("meta") or {}
    if str(meta.get("symbol", "")).upper() != mapped.upper():
        raise YahooDataError("provider symbol identity mismatch")
    if meta.get("currency") != "INR" or meta.get("exchangeTimezoneName") not in ("Asia/Kolkata", "Asia/Calcutta"):
        raise YahooDataError("required INR/NSE timezone provenance absent")
    if meta.get("instrumentType") not in ("EQUITY", "ETF", "INDEX"):
        raise YahooDataError("not an NSE cash/index instrument")
    timestamps = result.get("timestamp") or []
    quotes = (result.get("indicators") or {}).get("quote") or []
    if len(quotes) != 1 or not timestamps:
        raise YahooDataError("no OHLCV timestamps")
    fields = ("open", "high", "low", "close", "volume")
    series = quotes[0]
    if any(not isinstance(series.get(field), list) or len(series[field]) != len(timestamps) for field in fields):
        raise YahooDataError("unaligned OHLCV arrays")
    from research_data_contracts import default_calendar
    calendar = default_calendar()
    rows, outside, invalid, empty_slots, non_session_marks, latest_marks = [], 0, 0, [], [], []
    for index, seconds in enumerate(timestamps):
        stamp = datetime.fromtimestamp(seconds, IST)
        if not first <= stamp.date() <= last:
            outside += 1  # Yahoo can append its latest mark beyond period2.
            continue
        if all(series[field][index] is None for field in fields):
            # Yahoo emits timestamp placeholders even on some holidays. No
            # candle exists: record absence, not an invented invalid OHLC bar.
            empty_slots.append(stamp.isoformat())
            continue
        cells = []
        for field in fields:
            value = series[field][index]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                cells.append(None)
            else:
                cells.append(value)
        invalid += any(value is None for value in cells)
        if interval != "1d" and seconds == meta.get("regularMarketTime") and stamp.time() >= day_time(15, 30):
            if cells[4] == 0 and None not in cells and len(set(cells[:4])) == 1:
                latest_marks.append(stamp.isoformat())
                continue  # The provider's final quote mark is not an interval candle.
        if interval == "1d" and cells[4] == 0 and None not in cells and len(set(cells[:4])) == 1:
            closed = stamp.weekday() >= 5 or (calendar.covers(stamp.date()) and not calendar.is_trading_day(stamp.date()))
            if closed:
                non_session_marks.append(stamp.isoformat())
                continue  # A flat zero-volume holiday mark is not a session candle.
        if interval == "1d":
            rows.append([symbol, stamp.date().isoformat(), *cells])
        else:
            label = {"1m": "minute", "15m": "15minute"}[interval]
            rows.append([symbol, label, stamp.isoformat(), *cells])
    if not rows:
        raise YahooDataError("no rows inside requested inclusive dates")
    return rows, {"returned_rows": len(timestamps), "selected_rows": len(rows),
                  "out_of_window_rows": outside, "invalid_cells_rows": invalid,
                  "empty_provider_slots": empty_slots,
                  "non_session_marks": non_session_marks,
                  "latest_quote_marks": latest_marks,
                  "first": rows[0][1 if interval == "1d" else 2],
                  "last": rows[-1][1 if interval == "1d" else 2],
                  "currency": meta["currency"], "exchange_timezone": meta["exchangeTimezoneName"],
                  "instrument_type": meta["instrumentType"],
                  "corporate_actions": result.get("events", {}),
                  "price_basis": "Yahoo quote OHLC as returned; no local adjustment/repair; historical split basis may be revised"}


def fetch_chart(local: Path, symbol: str, mapped: str, interval: str,
                start: str, end: str, *, timeout: float = 20) -> tuple[list[list], dict]:
    parameters = {"period1": int(datetime.combine(iso_day(start), datetime.min.time(), IST).timestamp()),
                  "period2": int(datetime.combine(iso_day(end) + timedelta(days=1), datetime.min.time(), IST).timestamp()),
                  "interval": interval, "events": "div,splits", "includePrePost": "false"}
    url = ENDPOINT + quote(mapped, safe="") + "?" + urlencode(parameters)
    target = local / "raw" / f"{quote(mapped, safe='')}_{interval}_{start}_{end}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    receipt = {"symbol": symbol, "yahoo_symbol": mapped, "interval": interval,
               "start": start, "end": end, "source": SOURCE, "url": url,
               "fetched_at_utc": datetime.now(timezone.utc).isoformat()}
    data = None
    for attempt in range(2):
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0 TradingSentinelResearch/1.0"})
            try:
                response = urlopen(request, timeout=timeout)
            except HTTPError as exc:
                response = exc  # Archive structured Yahoo errors as evidence.
            with closing(response):
                status = response.code
                data = response.read(20_000_001)
                retry_after = response.headers.get("Retry-After")
            if len(data) > 20_000_000:
                raise YahooDataError("response exceeds bounded size")
            if status == 429 and attempt == 0:
                try: delay = min(30, max(2, int(retry_after or 2)))
                except ValueError: delay = 2
                time.sleep(delay)
                continue
            receipt["http_status"] = status
            break
        except (URLError, TimeoutError, OSError) as exc:
            receipt["transport_error"] = f"{type(exc).__name__}: {exc}"
            if attempt == 0:
                time.sleep(1)
    if data is None:
        return [], {**receipt, "state": "UNAVAILABLE", "reason": receipt.get("transport_error", "no response")}
    with target.open("xb") as handle:
        handle.write(data)
    receipt.update(raw_file=str(target.relative_to(local.parent)), raw_sha256=sha(target))
    try:
        rows, metadata = parse_chart(json.loads(data), symbol, mapped, interval, start, end)
        if receipt.get("http_status") != 200:
            raise YahooDataError(f"Yahoo HTTP {receipt.get('http_status')}")
        return rows, {**receipt, **metadata, "state": "AVAILABLE"}
    except (YahooDataError, ValueError, TypeError, KeyError, OverflowError) as exc:
        return [], {**receipt, "state": "UNAVAILABLE", "reason": f"{type(exc).__name__}: {exc}"}


def supplied_config(module: str, universe: dict) -> dict:
    if module == "penny-joint":
        return {"mis_tickers": universe["penny"], "cnc_tickers": universe["penny"]}
    return {"tickers": universe["penny" if module in ("penny-mis", "penny-cnc", "edge") else "stock"]}


def acquire(out: Path, args, universe: dict, mappings: dict) -> dict:
    local = out / "_local"
    local.mkdir()
    records, daily, intraday, availability = [], [], [], {}
    requested_names = sorted(set(universe["penny"] + universe["stock"] + list(CONTEXT)))
    intervals = sorted({INTRADAY[module] for module in args.modules if module in INTRADAY})
    diagnostic_start = max(iso_day(args.start), iso_day(args.end) - timedelta(days=max(1, args.intraday_diagnostic_days) - 1)).isoformat()
    windows = [("primary", args.start, args.end)]
    if args.intraday_diagnostic_days and diagnostic_start != args.start:
        windows.append(("recent-diagnostic", diagnostic_start, args.end))
    for kind, start, end in windows:
        for interval in intervals:
            first, last = chunks(start, end, interval)[0]
            _, receipt = fetch_chart(local, "NIFTY 50", "^NSEI", interval, first, last)
            records.append(receipt)
            availability[f"{kind}:{interval}"] = {"start": start, "end": end, "state": receipt["state"],
                                                    "reason": receipt.get("reason")}
            print(f"Yahoo {kind} {interval}: {receipt['state']} {receipt.get('reason', '')}", flush=True)
    tasks = []
    history_start = (iso_day(args.start) - timedelta(days=900)).isoformat()
    for name in requested_names:
        tasks.append((name, "1d", history_start, args.end))
    # Primary data covers diagnostic dates too. Otherwise download only the
    # explicitly declared diagnostic; never silently clip the primary request.
    for interval in intervals:
        key = f"primary:{interval}"
        window = availability[key]
        if window["state"] != "AVAILABLE":
            window = availability.get(f"recent-diagnostic:{interval}", {})
        if window.get("state") != "AVAILABLE":
            continue
        names_for_interval = universe["penny"] if interval == "1m" else universe["stock"]
        for name in names_for_interval:
            for start, end in chunks(window["start"], window["end"], interval):
                tasks.append((name, interval, start, end))
    print(f"Downloading {len(tasks)} Yahoo requests with {args.workers} workers", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = {pool.submit(fetch_chart, local, name, mappings[name], interval, start, end):
                   (name, interval) for name, interval, start, end in tasks}
        for number, future in enumerate(as_completed(pending), 1):
            rows, receipt = future.result()
            records.append(receipt)
            (daily if receipt["interval"] == "1d" else intraday).extend(rows)
            if number % 25 == 0 or number == len(tasks):
                print(f"Yahoo requests completed: {number}/{len(tasks)}", flush=True)
    # A successful response may still contain corrupt rows. B1 decides validity.
    snapshot = write_snapshot({"daily": daily, "intraday": intraday,
                               "request": {"start": args.start, "end": args.end,
                                           "history_start": history_start, "history_days": 900,
                                           "tickers": requested_names}}, str(local / "yahoo.sqlite"), source=SOURCE)
    manifest = {"source": SOURCE, "requested": [args.start, args.end], "universe": universe,
                "symbol_mapping": mappings, "snapshot": snapshot, "availability": availability,
                "windows": windows, "records": records, "history_start": history_start,
                "adjustment": "Provider quote OHLCV, no local adjustment or repair; action receipts retained",
                "retention_reference": "https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html"}
    _atomic_json_new(str(out / "provider-manifest.json"), manifest)
    return manifest


def reuse_yahoo(out: Path, source: Path, args) -> dict:
    manifest = json.loads((source / "provider-manifest.json").read_text())
    if manifest.get("source") != SOURCE or manifest.get("requested") != [args.start, args.end]:
        raise ValueError("offline source must be this Yahoo workflow and the identical requested dates")
    snapshot = verify_snapshot(str(source / "_local/yahoo.sqlite"))
    if snapshot != manifest["snapshot"]:
        raise ValueError("offline Yahoo snapshot manifest mismatch")
    for record in manifest["records"]:
        if record.get("raw_file"):
            raw = (source / record["raw_file"]).resolve()
            if not raw.is_relative_to(source.resolve()) or sha(raw) != record["raw_sha256"]:
                raise ValueError("offline Yahoo raw response changed")
    (out / "_local").mkdir()
    shutil.copyfile(source / "_local/yahoo.sqlite", out / "_local/yahoo.sqlite")
    shutil.copytree(source / "_local/raw", out / "_local/raw")
    # Raw provenance is linked to the verified source archive; no network/cache fallback.
    _atomic_json_new(str(out / "provider-manifest.json"), {**manifest, "verified_offline_source": str(source.resolve())})
    return manifest


def data_quality(out: Path, universe: dict, manifest: dict) -> tuple[dict, dict]:
    from research_data_contracts import load_daily_dataset, load_intraday_dataset
    db = str(out / "_local/yahoo.sqlite")
    all_names = sorted(set(universe["penny"] + universe["stock"] + list(CONTEXT)))
    daily = load_daily_dataset(db, tickers=all_names, before=(iso_day(manifest["requested"][1]) + timedelta(days=1)).isoformat())
    excluded = {name: "INVALID_DAILY_HISTORY" if name in daily.invalid else "NO_DAILY_HISTORY"
                for name in all_names if name in daily.invalid or not daily.bars.get(name)}
    effective = {family: [name for name in values if name not in excluded] for family, values in universe.items()}
    quality = {"daily": daily.manifest, "daily_exclusions": excluded, "requested_universe": universe,
               "effective_universe": effective, "selection_rule": "data validity/availability only, frozen before strategy scoring",
               "membership": "current explicitly configured symbols; historical membership unavailable",
               "intraday": {}}
    validated_intraday = {}
    for key, window in manifest["availability"].items():
        interval = key.split(":")[1]
        requested = universe["penny" if interval == "1m" else "stock"]
        data = load_intraday_dataset(db, interval="minute" if interval == "1m" else "15minute",
                                     start=window["start"], end=window["end"], tickers=requested)
        quality["intraday"][key] = {"provider_state": window["state"], "manifest": data.manifest,
                                   "coverage": data.coverage}
        for (symbol, _), bars in data.bars.items():
            for bar in bars:
                identity = (symbol, data.interval.label, bar.start.isoformat())
                row = [*identity, bar.open, bar.high, bar.low, bar.close, bar.volume]
                previous = validated_intraday.get(identity)
                if previous is not None and previous != row:
                    raise ValueError("conflicting validated interval identity")
                validated_intraday[identity] = row
    validated_daily = [[symbol, bar.day.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume]
                       for symbol, bars in daily.bars.items() if symbol not in excluded for bar in bars]
    quality["validated_snapshot"] = write_snapshot({"daily": validated_daily,
        "intraday": list(validated_intraday.values()), "request": manifest["snapshot"]["request"]},
        str(out / "_local/validated-yahoo.sqlite"), source=SOURCE + "; B1 whole-invalid-day exclusion; raw snapshot retained")
    _atomic_json_new(str(out / "coverage.json"), quality)
    return effective, quality


def normalize_trade_clocks(trades: list[dict]) -> list[dict]:
    result = copy.deepcopy(trades)
    for trade in result:
        for field in ("entry_time_utc", "exit_fill_ts"):
            if trade.get(field):
                stamp = datetime.fromisoformat(trade[field])
                if stamp.tzinfo is None:
                    raise ValueError("aware lifecycle clocks required for shared cash")
                trade[field] = stamp.astimezone(timezone.utc).isoformat()
    return result


def execute_module(out: Path, module: str, kind: str, start: str, end: str,
                   effective: dict, manifest: dict, quality: dict, results: dict,
                   *, gap_sensitivity: bool = False, baseline: dict | None = None,
                   orchestration_hash: str | None = None) -> dict:
    job = module if kind == "primary" else f"{module}-recent-diagnostic"
    if gap_sensitivity:
        job += "-gap-sensitivity"
    strategy = MODULES[module]
    if strategy is None:
        record = {"job": job, "module": module, "window_kind": kind, "dates": [start, end],
                  "state": "NOT_ADAPTED", "scope": "ADVISORY_ONLY", "metrics": None,
                  "reason": "Partner advisory/protection is not an OHLCV money-book replay; no adapter exists."}
        _atomic_json_new(str(out / f"{job}.json"), record)
        return record
    adapter = STRATEGY_REGISTRY[strategy]
    report = {"job": job, "module": module, "strategy_id": strategy, "window_kind": kind,
              "dates": [start, end], "scope": adapter.metadata.scope, "source": SOURCE,
              "qualification": "NOT_ASSESSED", "can_place_orders": False,
              "policy": policy_manifest(strategy, adapter), "snapshot": quality["validated_snapshot"],
              "orchestration_sha256": sha(Path(__file__)), "limitations": list(adapter.metadata.limitations),
              "requested_universe": quality["requested_universe"], "effective_universe": effective}
    config_input = supplied_config(module, effective)
    if gap_sensitivity:
        config_input["session_policy"] = "allow_gaps"
        report["limitations"].append("Declared partial-session sensitivity; does not replace complete-session primary.")
    try:
        config = adapter.snapshot_config(config_input)
    except ValueError as exc:
        config = config_input
        config_error = str(exc)
    else:
        config_error = None
    assumptions = adapter.snapshot_assumptions({})
    report["request"] = {"start": start, "end": end, "config": config, "assumptions": assumptions}
    _atomic_json_new(str(out / f"{job}-freeze.json"), report)
    print(f"{job}: frozen; executing {start} through {end}", flush=True)
    try:
        check_policy(report["policy"], baseline, orchestration_hash)
        if config_error:
            raise BacktestUnavailable(config_error)
        interval = INTRADAY.get(module)
        if interval and manifest["availability"].get(f"{kind}:{interval}", {}).get("state") != "AVAILABLE":
            reason = manifest["availability"].get(f"{kind}:{interval}", {}).get("reason", "no native interval evidence")
            raise BacktestUnavailable(f"Yahoo rejected requested {interval} window: {reason}")
        if module in ("swing", "edge"):
            context = ("NIFTY 50", "NIFTY BANK") if module == "swing" else ("NIFTYBEES",)
            missing = [name for name in context if name in quality["daily_exclusions"]]
            if missing:
                raise BacktestUnavailable("missing/invalid market context: " + ", ".join(missing))
        request = BacktestRequest(strategy, start, end, config, assumptions)
        if module == "penny-joint":
            from dataclasses import asdict
            from portfolio_parity import reconcile_shared_cash
            prior = [results.get(("penny-mis", kind, gap_sensitivity)), results.get(("penny-cnc", kind, False))]
            if any(not value or value.get("state") != "SUCCEEDED" for value in prior):
                raise BacktestUnavailable("joint cash requires successful same-window MIS and CNC lifecycle reports")
            mis, cnc = (value["result"] for value in prior)
            ledger = reconcile_shared_cash((("penny_mis", normalize_trade_clocks(mis["trades"])),
                                            ("penny_cnc", normalize_trade_clocks(cnc["trades"]))), initial_cash=config["initial_cash"])
            result = {"scope": "PORTFOLIO_PARTIAL", "status": "PARTIAL", "portfolio": asdict(ledger),
                      "warnings": ["Reuses same-window shipped lifecycles with UTC-normalized clocks; not live P1 fee/buffer admission."]}
            report["dataset_fingerprint"] = quality["validated_snapshot"]["rows_sha256"]
        else:
            prepared = adapter.prepare(str(out / "_local/validated-yahoo.sqlite"), request)
            result = adapter.execute(prepared, request)
            report.update(dataset_fingerprint=prepared.fingerprint, dataset=prepared.details)
        metrics, warnings = adapter.normalize(result, request)
        check_policy(policy_manifest(strategy, adapter), baseline, orchestration_hash)
        report.update(state="SUCCEEDED", result=result, metrics=metrics, warnings=warnings,
                      coverage_status="PARTIAL_UNIVERSE" if quality["daily_exclusions"] else "DATA_PRESENT_NOT_FULL_SYSTEM")
        if result.get("status") == "UNAVAILABLE":
            report.update(state="UNAVAILABLE", reason="no usable ticker-days after shipped lifecycle history/context checks", metrics=None)
        if module == "momentum":
            report["exit_fidelity"] = {"reasons": dict(Counter(t.get("exit_reason", "OPEN") for t in result["trades"])),
                                       "not_live_lifecycle": True}
            if report["exit_fidelity"]["reasons"].get("overnight_gap_exit"):
                report["warnings"].append("Later-day virtual exits exist: net result cannot estimate live MIS intraday performance.")
        results[(module, kind, gap_sensitivity)] = report
    except BacktestUnavailable as exc:
        report.update(state="UNAVAILABLE", reason=str(exc), metrics=None)
    except Exception as exc:
        report.update(state="FAILED", reason=f"{type(exc).__name__}: {exc}", metrics=None)
    raw = out / "_local" / f"{job}-report.json"
    _atomic_json_new(str(raw), report)
    receipt = {key: value for key, value in report.items() if key in (
        "job", "module", "strategy_id", "window_kind", "dates", "state", "scope", "reason", "metrics",
        "coverage_status", "exit_fidelity", "warnings", "qualification", "can_place_orders")}
    receipt.update(report_file=str(raw.relative_to(out)), report_sha256=sha(raw))
    _atomic_json_new(str(out / f"{job}.json"), receipt)
    print(f"{job}: {receipt['state']}; metrics={json.dumps(receipt.get('metrics'), separators=(',', ':'))[:300]}", flush=True)
    return receipt


def check_policy(actual: dict, expected: dict | None, orchestration_hash: str | None) -> None:
    if expected and any(actual[key] != expected[key] for key in ("engine_sha256", "settings_sha256")):
        raise BacktestUnavailable("source/settings changed during this run; freeze a new run")
    if orchestration_hash and sha(Path(__file__)) != orchestration_hash:
        raise BacktestUnavailable("Yahoo importer/orchestration changed during this run")


def render_summary(out: Path, records: list[dict], manifest: dict, quality: dict) -> None:
    summary = {"source": SOURCE, "requested_dates": manifest["requested"], "modules": records,
               "snapshot": manifest["snapshot"], "daily_exclusions": quality["daily_exclusions"],
               "qualification": "NOT_ASSESSED", "can_place_orders": False,
               "full_system_profit_available": False,
               "limitations": ["Yahoo OHLCV cannot supply historical manual/broker/context evidence.",
                               "Recent diagnostics do not replace the requested date window.",
                               "Evaluator candidates are not trades; partial books must not be summed into system profit.",
                               "Current universe/defaults, not point-in-time historical membership/configuration."]}
    _atomic_json_new(str(out / "summary.json"), summary)
    lines = ["# Yahoo-only current non-F&O backtests", "",
             f"Requested dates (inclusive IST): {manifest['requested'][0]} to {manifest['requested'][1]}.",
             "All market bars come from Yahoo; no Sentinel trade/price history is used.", "",
             "| Module/window | Dates | State/scope | Evidenced result |", "|---|---|---|---|"]
    for record in records:
        metrics = record.get("metrics") or {}
        if record["state"] != "SUCCEEDED":
            result = record.get("reason", "unavailable").replace("|", "/")
        elif record["scope"] == "EVALUATOR" and "candidate_count" in metrics:
            result = f"{metrics['candidate_count']} candidates; {metrics['selected_count']} selections; P&L unavailable"
        elif record["scope"] == "EVALUATOR" and "entry_decisions" in metrics:
            result = f"{metrics['entry_decisions']} ENTER decisions; P&L unavailable"
        else:
            net = metrics.get("net_pnl")
            result = f"count={metrics.get('trade_count')}; net={'unavailable' if net is None else round(net, 2)}; unresolved={metrics.get('unresolved_trades', metrics.get('shared_cash', {}).get('unresolved', 'see report'))}"
        lines.append(f"| {record['job']} | {' to '.join(record['dates'])} | {record['state']} / {record['scope']} | {result} |")
    lines += ["", f"Daily names excluded for missing/invalid evidence: {len(quality['daily_exclusions'])}.",
              "Coverage, per-symbol errors, raw hashes, policy/defaults and costs are archived beside this report.",
              "Recent diagnostics are separate shorter windows; evaluator results are not entry-to-exit portfolio performance.",
              "Momentum uses a virtual full-quantity T1 exit; inspect exit_fidelity for any later-day fallback settlements.",
              "Joint Penny count is admitted entries, not closed trades; locked notional is not marked equity.",
              "No qualification, aggregate system return, orders or deployment."]
    with (out / "summary.md").open("x", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def run(args) -> Path:
    first, last = iso_day(args.start), iso_day(args.end)
    now = datetime.now(IST)
    if first > last or last > now.date():
        raise ValueError("require start <= end <= today")
    from research_data_contracts import default_calendar
    calendar = default_calendar()
    if last == now.date() and now.time() < day_time(15, 30) and calendar.covers(last) and calendar.is_trading_day(last):
        raise ValueError("today's NSE session is unfinished; choose an earlier end date")
    if not 1 <= args.workers <= 8 or not 0 <= args.intraday_diagnostic_days <= 30:
        raise ValueError("workers must be 1..8; diagnostic days 0..30")
    args.modules = names(args.modules.lower())  # normalize separately below
    args.modules = [value.lower() for value in args.modules]
    unknown = set(args.modules) - set(MODULES)
    if unknown:
        raise ValueError("unknown/non-cash modules: " + ", ".join(sorted(unknown)))
    if "penny-joint" in args.modules:
        args.modules = sorted(set(args.modules) | {"penny-mis", "penny-cnc"})
    baseline = {module: policy_manifest(MODULES[module], STRATEGY_REGISTRY[MODULES[module]])
                for module in args.modules if MODULES[module]}
    orchestration_hash = sha(Path(__file__))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = args.out or ROOT / "docs/research/yahoo" / f"{stamp}_{args.start}_{args.end}"
    out = out.resolve()
    production = (ROOT.parent / "Production_Trading-sentinel").resolve()
    if out.is_relative_to(production):
        raise ValueError("Production output is forbidden")
    out.mkdir(parents=True, exist_ok=False)
    if args.offline:
        manifest = reuse_yahoo(out, args.offline.resolve(), args)
        universe = manifest["universe"]
        _atomic_json_new(str(out / "request-freeze.json"), {"source": SOURCE, "requested": [args.start, args.end],
            "modules": args.modules, "universe": universe, "offline_source": str(args.offline.resolve()),
            "policy_baselines": baseline, "orchestration_sha256": orchestration_hash, "can_place_orders": False})
    else:
        stock_path = args.stock_universe or ROOT / "python-engine/data/nifty500.json"
        penny_path = args.penny_universe or ROOT / "python-engine/data/penny_static.json"
        stock, penny = read_universe(stock_path), read_universe(penny_path)
        if not penny:
            penny_path = ROOT / "scripts/data/backtest_penny_universe.json"
            penny = read_universe(penny_path)
        if args.tickers:
            stock = penny = names(args.tickers)
        if not stock or not penny or len(set(stock + penny)) > 2000:
            raise ValueError("bounded nonempty explicit stock/Penny universes required")
        universe = {"stock": stock, "penny": penny}
        overrides = json.loads(args.symbol_map.read_text()) if args.symbol_map else {}
        mappings = {name: yahoo_symbol(name, overrides) for name in sorted(set(stock + penny + list(CONTEXT)))}
        if len(set(mappings.values())) != len(mappings):
            raise ValueError("multiple internal symbols mapped to the same Yahoo identity")
        _atomic_json_new(str(out / "request-freeze.json"), {"source": SOURCE, "requested": [args.start, args.end],
            "modules": args.modules, "universe": universe, "universe_files": [str(stock_path), str(penny_path)],
            "symbol_mapping": mappings, "intraday_diagnostic_days": args.intraday_diagnostic_days,
            "policy_baselines": baseline, "orchestration_sha256": orchestration_hash, "can_place_orders": False})
        manifest = acquire(out, args, universe, mappings)
    effective, quality = data_quality(out, universe, manifest)
    verify_snapshot(str(out / "_local/yahoo.sqlite"))
    verify_snapshot(str(out / "_local/validated-yahoo.sqlite"))
    results, receipts = {}, []
    # Cache MIS/CNC results for joint cash, while preserving their independent scopes.
    order = [name for name in MODULES if name in args.modules]
    for kind, start, end in manifest["windows"]:
        if kind != "primary" and not args.intraday_diagnostic_days:
            continue
        for module in order:
            if kind != "primary" and module not in INTRADAY:
                continue
            receipts.append(execute_module(out, module, kind, start, end, effective, manifest, quality, results,
                                           baseline=baseline.get(module), orchestration_hash=orchestration_hash))
            if module in ("penny-mis", "penny-joint"):
                receipts.append(execute_module(out, module, kind, start, end, effective, manifest, quality, results,
                                               gap_sensitivity=True, baseline=baseline.get(module), orchestration_hash=orchestration_hash))
    verify_snapshot(str(out / "_local/yahoo.sqlite"))
    verify_snapshot(str(out / "_local/validated-yahoo.sqlite"))
    render_summary(out, receipts, manifest, quality)
    print(f"Results: {out / 'summary.md'}", flush=True)
    return out


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--start", "--from", required=True)
    cli.add_argument("--end", "--to", required=True)
    cli.add_argument("--tickers", help="explicit comma-separated subset for both stock and Penny studies")
    cli.add_argument("--stock-universe", type=Path)
    cli.add_argument("--penny-universe", type=Path)
    cli.add_argument("--symbol-map", type=Path)
    cli.add_argument("--modules", default=",".join(MODULES))
    cli.add_argument("--workers", type=int, default=4)
    cli.add_argument("--intraday-diagnostic-days", type=int, default=7)
    cli.add_argument("--offline", type=Path, help="verify/reuse a prior Yahoo-only run, no network")
    cli.add_argument("--out", type=Path, help="new output directory; existing artifacts cannot be overwritten")
    return cli


if __name__ == "__main__":
    try:
        run(parser().parse_args())
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
