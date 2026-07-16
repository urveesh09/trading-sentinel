"""
[PENNY-UNIVERSE 2026-06-21] Penny-stock universe loader + eligibility filter.

Mirrors the structure of universe.py but is owned by the penny subsystem.
Loads a JSON file of penny candidates, validates each ticker against the
spec §2.3 eligibility gates, resolves to Kite instrument tokens via an
injected instrument_cache dict, and exposes the eligible set.

Hard architectural rule (enforced by tests/test_penny_isolation.py):
  this module MUST NOT import from engine, regime, risk_engine, portfolio,
  evaluate_signal, or evaluate_momentum_signal.

Allowed shared imports: kite_client, models (base only), config,
position_tracker, performance, analytics, stdlib.
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# [PENNY-SG-FILTER 2026-07-02] Belt-and-braces filter for non-equity
# instruments that Kite's /instruments/NSE sometimes surfaces with
# instrument_type=EQ. Today (2026-07-02) the penny_static.json contained
# ~20 Sovereign Gold Bond (SGB) tickers (`-SG` suffix like 597CG27-SG,
# 662RJ30-SG) and 4 ETFs (PHARMABEES, BSE500IETF, BFSI, ESG). These are
# not equity tickers -- they're bonds and exchange-traded funds that
# dilute the universe's liquidity scoring and confuse the scanner.
#
# Two layers of defence:
#   1. `_is_non_equity_symbol()` is checked in the refresh path
#      (refresh_from_kite) BEFORE a ticker enters the candidate list.
#   2. `eligible_tickers()` filters them again at scan time so a stale
#      penny_static.json from before this commit also gets cleaned.
#
# Patterns covered:
#   -SG / -SGX / -GS          Sovereign Gold Bond suffixes
#   BEES / ETF / GILT / ...   ETF name hints
#   ^\d+[A-Z]{2}\d+...$       Generic `<digits><state><number>` bond
#                             pattern (e.g. 597CG27-SG, 662RJ30-SG)
import re as _re_sgfilter

_NON_EQUITY_SUFFIXES = ("-SG", "-SGX", "-GS")
_NON_EQUITY_EXACT = frozenset({
    "PHARMABEES", "BSE500IETF", "BFSI", "ESG",
    "GOLDBEES", "LIQUIDBEES", "CPSEETF", "NIFTYBEES",
    "BANKBEES", "JUNIORBEES", "SHARIABEES", "ITBEES",
    "SETFNIF50", "SETFNIFBK", "SETFNN50", "MASPTOP50",
    "MON100", "MONIFTY500", "MAFANG", "HEALTHY",
})
_NON_EQUITY_NAME_HINTS = (
    "BEES", "ETF", "GILT", "LIQUID", "CPSE", "SETF",
    "SGB", "GOLDBOND",
)
# Generic bond-pattern: digits + 2 letters + 2 digits + optional
# alpha-suffix. Matches SGB formats like:
#   597CG27     (no suffix)
#   100RJ31A    (single letter suffix)
#   597CG27-SG  (-SG suffix; but -SG is caught by the suffix check above)
_BOND_PATTERN = _re_sgfilter.compile(r"^\d+[A-Z]{2}\d+[A-Z]?$")


def _is_non_equity_symbol(symbol: str) -> bool:
    """True if the symbol is a Sovereign Gold Bond, ETF, or other
    non-equity instrument that shouldn't be in a penny-stock universe.

    Used at both refresh time (refresh_from_kite) and at scan time
    (eligible_tickers) to keep the universe clean. See module-level
    comment for the rationale (PENNY-SG-FILTER 2026-07-02).
    """
    if not symbol:
        return True
    sym = symbol.strip().upper()
    if not sym:
        return True
    if sym in _NON_EQUITY_EXACT:
        return True
    for sfx in _NON_EQUITY_SUFFIXES:
        if sym.endswith(sfx):
            return True
    # NAME_HINTS is checked AFTER the suffix check because a
    # suffix match (e.g. "-SG") is a stronger signal than a name
    # hint (e.g. "BEES" embedded in a name). Also, NAME_HINTS like
    # "GILT" or "SGB" can collide with legitimate equity names, so
    # we require a word-boundary match rather than a substring.
    import re as _re_hints
    for hint in _NON_EQUITY_NAME_HINTS:
        # Match if the hint appears as a whole word OR is
        # contiguous at the start/end of the symbol. Avoids
        # false positives like "IT" matching "ITBEES" alone --
        # "BEES" is the stronger hint here.
        if _re_hints.search(rf"(^|_){_re_hints.escape(hint)}($|_)", sym):
            return True
    if _BOND_PATTERN.match(sym):
        return True
    return False


class UniverseError(Exception):
    """Raised when the penny JSON is missing, malformed, or invalid."""


class PennyUniverse:
    """
    Loads the penny ticker list from a static JSON file and applies
    spec §2.3 eligibility filters at construction time. Caches the
    result in-memory.

    instrument_cache is injected (not imported) so this module has no
    dependency on a live KiteClient instance. Production callers pass
    kite_client.KiteClient().instrument_cache; tests pass a fixture dict.
    """

    def __init__(self, json_path: str, instrument_cache: Optional[Dict[str, int]] = None):
        cache = instrument_cache if instrument_cache is not None else {}
        self._all_tickers: List[dict] = []
        self._tokens: set = set()
        self._token_to_symbol: Dict[int, str] = {}
        self._symbol_to_token: Dict[str, int] = {}
        self._as_of: Optional[str] = None  # [AUDIT-FIX-2.4]
        self._load(json_path, cache)

    def _load(self, json_path: str, instrument_cache: Dict[str, int]) -> None:
        if not os.path.exists(json_path):
            raise UniverseError(f"penny JSON not found at {json_path}")
        try:
            with open(json_path) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise UniverseError(f"penny JSON is malformed: {e}") from e

        if "tickers" not in data or not isinstance(data["tickers"], list):
            raise UniverseError("penny JSON missing 'tickers' array")

        # [AUDIT-FIX-2.4 2026-06-25] Capture as_of for staleness checks.
        # Pre-fix the universe JSON's as_of was ignored, so a stale
        # refresh (e.g. last refresh 3 days ago over a long weekend)
        # silently fed the scanner old data. Now we log a WARNING if
        # as_of is older than 1 day AND expose as_of via .as_of for
        # callers (the scanner can surface staleness in hourly reports).
        #
        # We do NOT refuse to load -- the operator-mandated constraint
        # is "don't block the system during market hours". Even a 7-day-
        # old universe is better than no scanner at all. We just make
        # the staleness LOUD so the operator fixes the refresh job.
        self._as_of = data.get("as_of")
        if self._as_of:
            try:
                from datetime import date, datetime as _dt
                as_of_date = _dt.strptime(self._as_of, "%Y-%m-%d").date()
                today = date.today()
                age_days = (today - as_of_date).days
                if age_days > 1:
                    logger.warning(
                        "penny_universe_stale as_of=%s age_days=%d "
                        "FIX=run run_penny_universe_refresh() (scheduled 08:00 IST). "
                        "Scanner continues with stale data; signals may "
                        "miss fresh eligibility changes.",
                        self._as_of, age_days,
                    )
                elif age_days < 0:
                    # as_of in the future -- clock skew or manual edit.
                    logger.warning(
                        "penny_universe_as_of_in_future as_of=%s "
                        "(clock skew or manual edit; treating as fresh)",
                        self._as_of,
                    )
            except ValueError:
                logger.warning(
                    "penny_universe_as_of_unparseable as_of=%r "
                    "(expected YYYY-MM-DD)",
                    self._as_of,
                )
        else:
            logger.warning(
                "penny_universe_no_as_of "
                "FIX=regenerate penny_static.json (regen writes as_of=YYYY-MM-DD)"
            )

        self._all_tickers = data["tickers"]
        missing = []
        for t in self._all_tickers:
            sym = t.get("symbol")
            tok = instrument_cache.get(sym)
            if tok is not None:
                self._tokens.add(tok)
                self._token_to_symbol[tok] = sym
                self._symbol_to_token[sym] = tok
            else:
                missing.append(sym)
        if missing:
            logger.warning(
                "penny_universe_tokens_unresolved count=%d sample=%s",
                len(missing),
                missing[:5],
            )

    @property
    def size(self) -> int:
        return len(self._all_tickers)

    @property
    def tokens(self) -> set:
        return set(self._tokens)

    @property
    def as_of(self) -> Optional[str]:
        """[AUDIT-FIX-2.4] Returns the as_of date from the universe JSON
        (YYYY-MM-DD), or None if the JSON doesn't have one. Callers
        (e.g. the hourly report) can surface this to surface staleness
        without re-parsing the file."""
        return self._as_of

    @property
    def age_days(self) -> Optional[int]:
        """[AUDIT-FIX-2.4] Days since the universe JSON was refreshed.
        None if as_of is missing or unparseable. Negative if as_of is
        in the future (clock skew)."""
        if not self._as_of:
            return None
        try:
            from datetime import date, datetime as _dt
            as_of_date = _dt.strptime(self._as_of, "%Y-%m-%d").date()
            return (date.today() - as_of_date).days
        except ValueError:
            return None

    def token_to_symbol(self, token: int) -> Optional[str]:
        return self._token_to_symbol.get(token)

    def symbol_to_token(self, symbol: str) -> Optional[int]:
        return self._symbol_to_token.get(symbol)

    def eligible_tickers(self) -> List[dict]:
        """
        Apply spec §2.3 eligibility gates and return the surviving
        ticker records (unranked; ranking is in the refresh job).

        Null-tolerant (2026-06-25 deviation): when promoter_holding_pct or
        pb_ratio is missing from the universe record (Kite corp-data
        endpoint empty + no fallback file), the ticker is NOT silently
        dropped. Instead, it passes with a `data_quality` flag set so the
        operator can see degraded universe quality in the pre-market
        digest and the hourly report. Hard rejects (real promoter > 75%,
        real PB > 2.0) still apply when data IS available.

        Rationale: spec §2.3 promoter + PB gates are about avoiding
        shell / promoter-heavy / distressed names. The intent is
        preserved when data is present; when data is missing, downstream
        gates (volume surge 3x median, RS breakout, RSI<70) still filter
        to high-conviction setups, and the per-trade risk caps
        (Rs 500/stock, 5 positions, 5%/trade) limit damage if a
        low-quality name sneaks through.
        """
        from config import settings
        out = []
        # [PENNY-SG-FILTER 2026-07-02] Defence layer 2: drop SGB /
        # ETF / bond tickers even if a stale penny_static.json from
        # before this commit still contains them. The first guard is
        # cheap (string operations) so we run it before the rest of
        # the eligibility filter.
        for t in self._all_tickers:
            sym = t.get("symbol")
            # [PENNY-SG-FILTER 2026-07-02] Defence layer 2.
            if _is_non_equity_symbol(sym):
                continue
            if sym not in self._symbol_to_token:
                continue  # not resolvable; skip

            # Series gate: EQ only
            if t.get("series") != "EQ":
                continue

            # Price band gate (using prev_close as proxy at refresh time)
            pc = t.get("prev_close")
            if pc is None or pc < settings.PENNY_PRICE_MIN or pc > settings.PENNY_PRICE_MAX:
                continue

            # Liquidity gate
            tv = t.get("median_traded_value_20d", 0) or 0
            if tv < settings.PENNY_MIN_20D_TV:
                continue

            # Segment gates
            if t.get("is_t2t"):
                continue
            if t.get("is_asm"):
                continue
            if t.get("is_gsm"):
                continue

            # Promoter gate: strictly > 25% AND strictly < 75%.
            # Storage convention: universe JSON stores promoter_holding_pct
            # as a percentage (0-100). Settings store the threshold as a
            # fraction (0-1) for human readability ("0.75" is easier to read
            # than "75.0"). Convert settings to percent at compare time.
            #
            # Null tolerance (2026-06-25): missing promoter data is
            # tagged `data_quality=DEGRADED_promoter_missing` rather than
            # dropping the ticker. Hard rejects still apply when present.
            prom = t.get("promoter_holding_pct")
            data_quality_flags = []
            if prom is None:
                data_quality_flags.append("promoter_missing")
            else:
                if prom <= settings.PENNY_MIN_PROMOTER_HOLD * 100:
                    continue
                if prom >= settings.PENNY_MAX_PROMOTER_HOLD * 100:
                    continue

            # P/B gate: <= 2.0 (null tolerance mirrors promoter above)
            pb = t.get("pb_ratio")
            if pb is None:
                data_quality_flags.append("pb_missing")
            else:
                if pb > settings.PENNY_MAX_PB_RATIO:
                    continue

            # Tag the record with quality flags so downstream observers
            # (pre-market digest, hourly report) can surface degradation.
            if data_quality_flags:
                t = dict(t)  # do not mutate the cached dict
                t["data_quality"] = "DEGRADED:" + ",".join(data_quality_flags)
            out.append(t)
        return out

    def quality_audit(self) -> dict:
        """
        Summarise data quality of the currently loaded universe.
        Returns counts of tickers with null / missing fields that the
        eligibility filter would have used pre-2026-06-25 deviation.

        Used by the daily refresh job to log
        `penny_universe_quality_audit` and by the hourly report to
        surface degraded-universe warnings.
        """
        total = len(self._all_tickers)
        null_promoter = 0
        null_pb = 0
        null_tv = 0
        null_pc = 0
        for t in self._all_tickers:
            if t.get("promoter_holding_pct") is None:
                null_promoter += 1
            if t.get("pb_ratio") is None:
                null_pb += 1
            if not t.get("median_traded_value_20d"):
                null_tv += 1
            if t.get("prev_close") is None:
                null_pc += 1
        return {
            "total": total,
            "null_promoter": null_promoter,
            "null_pb": null_pb,
            "null_tv": null_tv,
            "null_pc": null_pc,
            "degraded_pct": round(
                100.0 * max(null_promoter, null_pb) / max(total, 1), 1
            ),
        }

    # ---- ranking + refresh (spec §2.4) -----------------------------------

    # Spec §2.4 composite-score weights
    RANK_WEIGHTS = {
        "momentum": 0.40,     # 20d avg daily return
        "liquidity": 0.30,    # 20d median traded value
        "low_distance": 0.20,  # distance from 52-week low (capped)
        "volatility": 0.10,   # 20d realized volatility
    }

    @staticmethod
    def _normalize(values):
        """Min-max normalize a list of numbers to [0, 1]. Handles empty + constant cases."""
        if not values:
            return []
        lo, hi = min(values), max(values)
        if hi == lo:
            return [0.5 for _ in values]
        return [(v - lo) / (hi - lo) for v in values]

    @classmethod
    def rank_tickers(cls, tickers, top_n=100):
        """
        Spec §2.4: composite-score ranking. Returns the top_n tickers.

        Each ticker record is expected to have:
          - avg_return_20d (float, can be negative)
          - median_traded_value_20d (float)
          - dist_from_52w_low_pct (float in [0, 1], capped at 0.95)
          - vol_20d (float, realized volatility)

        Composite = 0.40*norm(momentum) + 0.30*norm(liquidity)
                    + 0.20*norm(low_distance) + 0.10*norm(volatility)

        Negative momentum ranks below positive (we don't clip). This is
        intentional per spec: the "top 100 performing" list should bias
        toward positive momentum without excluding negative names entirely
        (since negative momentum + low PB = contrarian setup).
        """
        if not tickers:
            return []

        # Pre-process: cap low_distance at 0.95 so a single runaway can't
        # dominate that axis.
        capped = []
        for t in tickers:
            tt = dict(t)
            tt["dist_from_52w_low_pct"] = min(tt.get("dist_from_52w_low_pct", 0) or 0, 0.95)
            capped.append(tt)

        n = len(capped)
        mom = cls._normalize([t.get("avg_return_20d", 0) or 0 for t in capped])
        liq = cls._normalize([t.get("median_traded_value_20d", 0) or 0 for t in capped])
        dst = cls._normalize([t.get("dist_from_52w_low_pct", 0) or 0 for t in capped])
        vol = cls._normalize([t.get("vol_20d", 0) or 0 for t in capped])

        w = cls.RANK_WEIGHTS
        scored = []
        for i, t in enumerate(capped):
            score = w["momentum"] * mom[i] + w["liquidity"] * liq[i] + \
                    w["low_distance"] * dst[i] + w["volatility"] * vol[i]
            scored.append((score, t))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:top_n]]


async def _compute_one_history_metric(kite, sym: str, from_date: str, to_date: str) -> tuple:
    """
    [PENNY-CORP-PARALLEL 2026-06-30] One per-ticker history fetch + compute.
    Extracted from the main loop so asyncio.gather can fan the 100
    tickers out in parallel (the rate limiter is global, so we
    don't violate Kite's 3 req/s; gather just lets the limiter
    queue all requests at once instead of N serial round-trips).

    The earlier implementation made two sequential get_historical
    calls per symbol (short window + 52w). The 52w fetch is a
    superset, so we use ONE call with the longer window and
    derive both the 30d metrics AND the 52w-low distance from
    it. Halves the API call count.
    """
    try:
        df = await kite.get_historical(sym, from_date, to_date)
    except Exception as e:
        logger.warning(
            "penny_metrics_history_fetch_failed symbol=%s error=%s",
            sym, str(e),
        )
        return (sym, None)
    if df is None or df.empty or len(df) < 10:
        return (sym, None)
    try:
        df = df.sort_index()
        close = df["close"].astype(float)
        volume = df["volume"].astype(float)
        traded_value = close * volume
        tv_20d = float(traded_value.tail(20).median())
        log_ret = (close / close.shift(1)).dropna().apply(
            lambda x: float(x) if x > 0 else float("nan")
        ).dropna()
        if len(log_ret) >= 2:
            avg_ret_20d = float(log_ret.tail(20).mean())
            vol_20d = float(log_ret.tail(20).std(ddof=0))
        else:
            avg_ret_20d = 0.0
            vol_20d = 0.0
        low_52w = float(df["low"].astype(float).min())
        last_close = float(close.iloc[-1])
        if low_52w > 0:
            dist = (last_close - low_52w) / low_52w
            dist_52w = float(min(max(dist, 0.0), 0.95))
        else:
            dist_52w = 0.0
        return (sym, {
            "median_traded_value_20d": tv_20d,
            "avg_return_20d": avg_ret_20d,
            "vol_20d": vol_20d,
            "dist_from_52w_low_pct": dist_52w,
            "bars_used": int(len(df)),
        })
    except Exception as e:
        logger.warning(
            "penny_metrics_compute_failed symbol=%s error=%s",
            sym, str(e),
        )
        return (sym, None)


async def compute_metrics_from_history(kite, symbols, lookback_days: int = 30) -> Dict[str, dict]:
    """
    [PENNY-CORP-FALLBACK 2026-06-26] Compute the four corp-data metrics the
    universe needs (median_traded_value_20d, avg_return_20d, vol_20d,
    dist_from_52w_low_pct) directly from Kite's daily history per ticker.

    Why this exists
    ---------------
    `KiteClient.get_corporate_actions()` always returns [] -- Kite Connect
    does not expose a corporate-actions / fundamental-data endpoint. The
    refresh job's fallback path (`penny_company_data.json`) only works if a
    human-curated file is on disk; in the container it does not exist.
    Result: median_traded_value_20d has been 0 for every ticker, the
    eligibility liquidity gate kills all 100, and the scanner produces
    0 signals every day (see 2026-06-26 incident).

    This helper fills those fields from daily history, which IS available
    via kite.get_historical. One round-trip per ticker; Kite self-throttles
    at 3 req/s and the call is SQLite-cached, so the 08:00 IST daily refresh
    pays ~30s on day 1 and is essentially free from day 2 onwards.

    [PENNY-CORP-PARALLEL 2026-06-30] Parallelised with asyncio.gather.
    The earlier serial loop took 1h 38min on the first prod run because
    each per-ticker Kite call costs ~10-30s end-to-end (network +
    parse + SQLite write). 100 tickers serially = 100 × 20s = 33 min,
    and 2 sequential calls per ticker (short window + 52w) doubled
    that to 1h+. Now: (a) ONE call per ticker using the 52w window
    (the 30d metrics can be derived from the trailing 20 rows of
    the long fetch); (b) asyncio.gather fans all 100 calls out in
    parallel; the global Kite rate limiter queues them at 3 req/s
    so the wall-clock cost is ~100/3 = 33s. Measured: 35-50s in
    subsequent runs (cache hot).

    [PENNY-HISTORY-SEMAPHORE 2026-07-07] Bound the concurrent sqlite
    opens with an asyncio.Semaphore. The 2026-07-07 incident showed that
    fanning 9,769 symbols out via `asyncio.gather` without bound causes
    every call to `kite.get_historical` -> `aiosqlite.connect(db_path)`
    to raise `OperationalError: unable to open database file` (rule 63
    in trading-sentinel-ops). The Kite API rate limiter (3 req/s)
    queues the HTTP calls fine, but the gather spawns 9,769 coroutines
    that all try to open the same SQLite file simultaneously. SQLite
    (even in WAL mode) returns EAGAIN/EACCES under that contention.
    Capping concurrent sqlite opens at HISTORY_SQLITE_MAX_CONCURRENT
    (=50 by default) eliminates the file-handle pressure while keeping
    the gather's effective parallelism well above the Kite rate limit.

    Metrics
    -------
      median_traded_value_20d : median(close * volume) over the trailing
        `lookback_days` calendar days of daily bars. In Rs (NOT crore).
        Liquidity gate compares this against PENNY_MIN_20D_TV.
      avg_return_20d          : mean of daily log returns over the same
        window. Used by the ranker's momentum weight (40%).
      vol_20d                 : stddev of daily log returns. Used by
        the ranker's volatility weight (10%).
      dist_from_52w_low_pct   : (last_close - 52w_low) / 52w_low, capped
        at 0.95 so far-from-low names don't dominate the ranker. Used by
        the ranker's low_distance weight (10%). Requires ~250 daily bars;
        if the window doesn't reach back that far we approximate with the
        full available history (capped lower bound).

    Returns
    -------
    Dict[str, dict] keyed by tradingsymbol. Each value has the four
    fields above plus a `bars_used` counter for observability. Symbols
    whose get_historical call returns empty / raises / has < 10 bars are
    omitted entirely -- the caller treats that as "no data" and falls
    back to the (existing) null-tolerance path in the eligibility filter.

    Failures
    --------
    Per-symbol errors are swallowed and logged at WARNING. A single bad
    ticker never blocks the others. The whole function never raises;
    callers can treat an empty dict the same as "no fallback data".
    """
    from datetime import timedelta
    import time as _time

    if not symbols:
        return {}

    # ONE fetch per symbol using the 52w window. The trailing 20 rows
    # give us the 30d metrics; the full window gives us the 52w low.
    # The 30d version (lookback_days + 10) is what we previously
    # used for the short pass; using 52w instead means the rate
    # limiter queues 100 calls instead of 200.
    from_52w = (datetime.utcnow() - timedelta(days=370)).strftime("%Y-%m-%d")
    to_date = datetime.utcnow().strftime("%Y-%m-%d")

    # [PENNY-HISTORY-SEMAPHORE 2026-07-07] Bounded concurrency over
    # the per-ticker sqlite open. The semaphore is acquired inside the
    # gather so the parallelism is CAPPED at HISTORY_SQLITE_MAX_CONCURRENT
    # (=50) regardless of len(symbols). 50 is well above Kite's 3 req/s
    # HTTP rate limit (so we don't bottleneck on the API) but well below
    # the OS-level file-handle ceiling on /data/cache.db. Tunable via
    # settings.PENNY_HISTORY_SQLITE_MAX_CONCURRENT.
    from config import settings as _settings
    max_concurrent = int(getattr(
        _settings, "PENNY_HISTORY_SQLITE_MAX_CONCURRENT", 50
    ))
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _bounded(metric_symbol: str):
        async with semaphore:
            return await _compute_one_history_metric(
                kite, metric_symbol, from_52w, to_date
            )

    t0 = _time.monotonic()
    results = await asyncio.gather(*[_bounded(s) for s in symbols])
    elapsed = _time.monotonic() - t0

    out: Dict[str, dict] = {}
    skipped: List[str] = []
    for sym, metrics in results:
        if metrics is None:
            skipped.append(sym)
            continue
        out[sym] = metrics
    if skipped:
        logger.warning(
            "penny_metrics_history_skipped count=%d sample=%s",
            len(skipped), skipped[:5],
        )
    # [PENNY-METRICS-COMPUTED 2026-07-07] This line is the only signal
    # the operator has that history-derived metrics were applied. The
    # 2026-07-07 incident proved this CAN go silent (all 9,769 calls
    # failed); making it WARNING-level when 0 metrics succeeded and
    # adding the `applied=count` k=v pair makes the rule-60 diagnostic
    # tree answer "did history fallback work today?" in one grep.
    level = logger.warning if len(out) == 0 else logger.info
    level(
        "penny_metrics_history_computed applied=%d skipped=%d "
        "elapsed=%.1fs max_concurrent=%d total_symbols=%d",
        len(out), len(skipped), elapsed, max_concurrent, len(symbols),
    )
    return out


def _repo_seed_path() -> str:
    """Path to the git-tracked corp-data seed (tier-3 fallback).

    __file__ is /app/penny_universe.py in the container (Dockerfile WORKDIR=/app
    COPY . .), so the in-repo data dir is the SAME dir as penny_universe.py, not
    a parent. Resolve via os.path.dirname(__file__) + 'data' -- NOT dirname-twice
    which would walk past python-engine/. Wrapped in a function so tests can
    monkeypatch it to exercise the "all tiers empty -> missing" path in
    isolation from whatever seed the repo happens to ship.
    """
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "penny_company_data.json"
    )


def _universe_audit_is_degraded(audit: dict, corp_source: Optional[str]) -> bool:
    """Decide whether penny_universe_quality_audit should log at WARNING.

    [PENNY-CORP-DEGRADE-WARN 2026-07-16] The 2026-07-07 fix escalated to
    WARNING when tv or pc was null on EVERY ticker (compute_metrics_from_history
    failing for all symbols) but left corporate fundamentals out of the
    condition. Consequence: a universe with corp_source="missing" and 100/100
    null promoter+pb logged at INFO and hid in plain sight -- and because the
    promoter (>25% & <75%) and P/B (<=2.0) gates are null-tolerant, every penny
    breakout was accepted with those two safety gates silently bypassed. A
    broken corp-data pipeline (corp_source missing) or fundamentals that are
    null on every ticker is exactly as degraded as null tv/pc and must be
    equally loud, so a single `grep penny_universe_quality_audit` answers
    "is today's universe quality OK?".
    """
    total = audit["total"]
    if total == 0:
        return True
    all_null_tv = audit["null_tv"] == total
    all_null_pc = audit["null_pc"] == total
    all_null_fundamentals = (
        audit["null_promoter"] == total and audit["null_pb"] == total
    )
    corp_missing = corp_source in ("missing", None)
    return (
        all_null_tv
        or all_null_pc
        or all_null_fundamentals
        or corp_missing
    )


async def refresh_from_kite(kite, out_json_path, corp_json_path, top_n=100):
    """
    Daily universe-refresh job (spec §2.4 + §9.1).

    1. Fetch NSE EQ instruments from Kite
    2. Fetch last price + previous close + volume per instrument
    3. Fetch corporate actions (promoter_holding_pct, pb_ratio, segment flags)
       or fall back to penny_company_data.json if Kite endpoint missing
    4. Apply PennyUniverse eligibility gates (price band, liquidity, promoter, PB)
    5. Compute 20d momentum + 52w-low distance + realized vol per ticker
    6. Rank via composite score
    7. Write top_n to penny_static.json
    8. Emit penny_universe_quality_audit (2026-06-25) so operators can
       see degraded-universe conditions without waiting for the hourly
       report to surface them.

    Failures must NOT crash the daily scheduler -- log + return None.
    """
    try:
        from config import settings
        # 1. Instruments
        instruments = await kite.get_instruments_nse_eq()
        # 2. Quotes (batched -- Kite's /quote URL has a length limit, so
        # passing ~2000 tokens at once raises "URL component 'query'
        # too long". Batch by 500 tokens per call.)
        #
        # If ALL batches return empty (e.g., Kite outage, network
        # failure during peak hours), do NOT overwrite the existing
        # penny_static.json with an empty universe. The scanner will
        # keep using the previous file until next refresh.
        all_tokens = [i["instrument_token"] for i in instruments]
        quotes: dict = {}
        failed_batches = 0
        total_batches = 0
        batch_size = 500
        for start in range(0, len(all_tokens), batch_size):
            total_batches += 1
            batch = all_tokens[start:start + batch_size]
            try:
                chunk = await kite.get_quote(batch)
                if isinstance(chunk, dict) and chunk:
                    quotes.update(chunk)
                else:
                    failed_batches += 1
                    logger.warning(
                        "penny_universe_quote_batch_empty start=%d size=%d",
                        start, len(batch),
                    )
            except Exception as e:
                failed_batches += 1
                logger.warning(
                    "penny_universe_quote_batch_failed start=%d size=%d error=%s",
                    start, len(batch), str(e),
                )
        if total_batches > 0 and failed_batches == total_batches:
            # All batches failed -- do NOT overwrite the universe file
            # with empty data. Caller will see this and skip writing.
            logger.error(
                "penny_universe_quote_all_batches_failed count=%d -- aborting refresh",
                total_batches,
            )
            return None
        if not quotes:
            logger.warning(
                "penny_universe_quote_empty total_batches=%d -- continuing with empty quote set",
                total_batches,
            )
        # 3. Corporate actions (with fallback)
        corp_source = "kite"  # tracked for audit logging
        try:
            corp = await kite.get_corporate_actions()
        except Exception:
            corp = None
        if not corp:
            # Primary fallback: the operator-curated file at the named
            # volume path (set via PENNY_CORP_DATA_JSON_PATH).
            try:
                with open(corp_json_path) as f:
                    corp_data = json.load(f)
                corp = corp_data.get("records", [])
                corp_source = "fallback_file"
            except Exception:
                corp = []
                corp_source = "missing"
            # [PENNY-CORP-FALLBACK-3 2026-07-07] If the named-volume
            # file is missing or empty, ALSO check the in-repo seed file
            # at python-engine/data/penny_company_data.json. This is the
            # docker-logs-observability rule's "the repo's data/ is
            # git-tracked seed data, the runtime reads from the named
            # volume" pitfall: in a fresh deployment the volume is
            # empty, but the repo has a curated (or empty) seed the
            # operator wants used as a third tier. The seed is treated
            # as a WORSE fallback than the named-volume file (which the
            # operator actively curates), but still better than nothing.
            if not corp:
                repo_seed = _repo_seed_path()
                try:
                    with open(repo_seed) as f:
                        seed_data = json.load(f)
                    seed_corp = seed_data.get("records", [])
                    if seed_corp:
                        corp = seed_corp
                        corp_source = "fallback_repo_seed"
                        logger.warning(
                            "penny_corp_data_falling_back_to_repo_seed "
                            "path=%s count=%d -- named-volume file is "
                            "empty/missing, using repo seed. Deploy the "
                            "named-volume file with curated data ASAP.",
                            repo_seed, len(corp),
                        )
                except Exception:
                    pass  # no seed either; corp stays []
        if not corp:
            logger.warning(
                "penny_corp_data_missing kite=empty fallback_file=%s -- "
                "universe will have null promoter_holding_pct and pb_ratio "
                "(eligibility filter is now null-tolerant, see deviation "
                "2026-06-25-penny-eligibility-null-tolerance.md). "
                "FIX=run penny_universe_refresh once corp-data is curated; "
                "until then, liquidity + momentum fields are derived from "
                "Kite history (compute_metrics_from_history).",
                corp_json_path,
            )
        corp_by_sym = {c.get("symbol"): c for c in (corp or [])}

        # [PENNY-CORP-FALLBACK 2026-06-26] If the corp-data source is
        # empty/missing, derive the four numeric metrics from Kite's daily
        # history per symbol. This unblocks the eligibility liquidity gate
        # (PENNY_MIN_20D_TV) which has been killing every ticker with tv=0.
        # Pre-existing fields from `corp_by_sym` are NOT overwritten --
        # history-derived values only fill where the corp record is missing
        # the field. See docs/deviations/2026-06-26-penny-corp-from-history.md
        symbols_for_metrics = [inst["tradingsymbol"] for inst in instruments]
        try:
            history_metrics = await compute_metrics_from_history(kite, symbols_for_metrics)
        except Exception as e:
            logger.warning(
                "penny_metrics_history_failed error=%s -- continuing with corp-only data",
                str(e),
            )
            history_metrics = {}
        if history_metrics:
            for sym, hm in history_metrics.items():
                rec = corp_by_sym.setdefault(sym, {})
                for k in ("median_traded_value_20d", "avg_return_20d",
                          "vol_20d", "dist_from_52w_low_pct"):
                    if rec.get(k) in (None, 0) and hm.get(k) is not None:
                        rec[k] = hm[k]
            logger.info(
                "penny_metrics_history_applied symbols=%d (filled missing corp fields)",
                len(history_metrics),
            )

        # 4-5. Build candidate records (eligibility filters happen here)
        # [PENNY-SEGMENT-FILTER 2026-06-26] Reject NSE non-EQ segments
        # (SME = "-SM"/"-ST" suffix, BE = "-BE", BZ = "-BZ", etc.). The
        # Kite filter in kite_client.get_instruments_nse_eq() relies on
        # `instrument_type=="EQ"` returning only the standard NSE EQ
        # series, but in practice some SME/BE symbols surface with
        # instrument_type=EQ in certain Kite responses -- leaving the
        # universe full of un-tokenisable tickers and the scanner
        # producing 0/0/0 forever. Defence in depth: also reject by
        # tradingsymbol suffix here so the refresh cannot accidentally
        # pick up non-standard segments regardless of Kite behaviour.
        # Counter is logged so the operator can see the leak size.
        sm_be_rejected = 0
        # [PENNY-SG-FILTER 2026-07-02] Defence layer 1 counter.
        non_equity_rejected = 0
        candidates = []
        for inst in instruments:
            sym = inst["tradingsymbol"]
            tok = inst["instrument_token"]
            q = quotes.get(tok) if isinstance(quotes, dict) else None
            if not q:
                continue
            # Standard NSE EQ segments: EQ only. Anything else (SM, BE,
            # BZ, IL, GS) is a non-standard series; reject.
            series = (inst.get("series") or "EQ").upper()
            if series != "EQ":
                sm_be_rejected += 1
                continue
            # Belt-and-braces: some Kite responses report series=EQ for
            # SME tickers too. Filter by tradingsymbol suffix as well.
            for bad_suffix in ("-SM", "-ST", "-BE", "-BZ", "-IL", "-GS"):
                if sym.endswith(bad_suffix):
                    sm_be_rejected += 1
                    break
            else:
                # [PENNY-SG-FILTER 2026-07-02] Defence layer 1: drop
                # Sovereign Gold Bonds, ETFs and other non-equity
                # instruments that Kite sometimes surfaces with
                # instrument_type=EQ. Without this, today's universe
                # contained ~20 SG bonds + 4 ETFs that polluted the
                # top-100 ranker. See module-level comment.
                if _is_non_equity_symbol(sym):
                    non_equity_rejected += 1
                    continue
                prev_close = q.get("ohlc", {}).get("close") or q.get("last_price")
                if prev_close is None:
                    continue
                corp_rec = corp_by_sym.get(sym, {})
                tv_20d = corp_rec.get("median_traded_value_20d", 0) or 0
                cand = {
                    "symbol": sym,
                    "series": series,
                    "prev_close": prev_close,
                    "promoter_holding_pct": corp_rec.get("promoter_holding_pct"),
                    "pb_ratio": corp_rec.get("pb_ratio"),
                    "is_t2t": corp_rec.get("is_t2t", False),
                    "is_asm": corp_rec.get("is_asm", False),
                    "is_gsm": corp_rec.get("is_gsm", False),
                    "median_traded_value_20d": tv_20d,
                    # momentum metrics populated below
                    "avg_return_20d": corp_rec.get("avg_return_20d", 0) or 0,
                    "dist_from_52w_low_pct": corp_rec.get("dist_from_52w_low_pct", 0) or 0,
                    "vol_20d": corp_rec.get("vol_20d", 0) or 0,
                }
                candidates.append(cand)
        if sm_be_rejected:
            logger.info(
                "penny_universe_segment_filtered count=%d "
                "(rejected NSE non-EQ series: SM/BE/ST/BZ/IL/GS)",
                sm_be_rejected,
            )
        if non_equity_rejected:
            logger.info(
                "penny_universe_non_equity_filtered count=%d "
                "(rejected SG bonds, ETFs and other non-equity tickers)",
                non_equity_rejected,
            )

        # Apply price-band eligibility only here (the full eligibility
        # filter with promoter/PB re-runs at scan time via PennyUniverse.eligible_tickers).
        in_band = [c for c in candidates
                   if settings.PENNY_PRICE_MIN <= c["prev_close"] <= settings.PENNY_PRICE_MAX]

        # 6. Rank
        ranked = PennyUniverse.rank_tickers(in_band, top_n=top_n)

        # 7. Write
        payload = {
            "as_of": datetime.utcnow().strftime("%Y-%m-%d"),
            "universe_size_target": top_n,
            "tickers": ranked,
        }
        os.makedirs(os.path.dirname(out_json_path), exist_ok=True)
        with open(out_json_path, "w") as f:
            json.dump(payload, f, indent=2)
        logger.info("penny_universe_refreshed count=%d", len(ranked))

        # 8. Quality audit (2026-06-25): write a temporary PennyUniverse
        # instance just to compute the audit (avoids re-reading the file
        # after we just wrote it; uses the in-memory `ranked` list).
        try:
            audit_universe = PennyUniverse.__new__(PennyUniverse)
            audit_universe._all_tickers = ranked
            audit_universe._tokens = set()
            audit_universe._token_to_symbol = {}
            audit_universe._symbol_to_token = {}
            audit = audit_universe.quality_audit()
            audit["corp_source"] = corp_source
            # [PENNY-QUALITY-AUDIT 2026-07-07] Promote the audit to
            # WARNING whenever ANY of the four numeric fields is missing
            # on EVERY ticker (the 2026-07-07 incident: 100/100 had
            # null_tv because compute_metrics_from_history silently
            # failed for every symbol; the universe file was written
            # "successfully" with 100 all-zero tickers and the operator
            # had no loud signal until the 30s scanner started logging
            # `penny_scan_no_eligible_universe` minutes later). With
            # this fix, the audit line itself surfaces a degraded
            # universe as a WARNING the moment it's detected, so a
            # single `grep penny_universe_quality_audit` answers
            # "is today's universe quality OK?" in 5 seconds.
            is_degraded = _universe_audit_is_degraded(audit, corp_source)
            level = logger.warning if is_degraded else logger.info
            level(
                "penny_universe_quality_audit "
                "total=%d null_promoter=%d null_pb=%d null_tv=%d "
                "null_pc=%d degraded_pct=%.1f corp_source=%s",
                audit["total"], audit["null_promoter"], audit["null_pb"],
                audit["null_tv"], audit["null_pc"], audit["degraded_pct"],
                corp_source,
            )
        except Exception as e:
            logger.warning("penny_universe_quality_audit_failed error=%s", str(e))

        return ranked
    except Exception as e:
        logger.error("penny_universe_refresh_failed error=%s", str(e))
        return None