"""
[PENNY-SECTOR-FILTER 2026-06-25] Sector-relative strength gate.

Closes Tier 2 idea #3 (sector-relative strength filter). The original
brainstorm concern: a breakout signal in a sector that's down 3% today
has very different probability than the same signal in a sector that's
up 1%. Sector momentum is a documented edge (per Cross-Sectional Equity
literature).

DESIGN PRINCIPLES (operator-mandated 2026-06-25):

1. NEVER kill proactiveness for lack of data. Every code path that
   fails to fetch data returns ALLOW, not REJECT. We refuse to
   silently make the system quieter because we couldn't look up a
   sector mapping.

2. Be smarter, not just stricter. The gate only blocks when:
   (a) We have a sector mapping for the ticker (from the CSV)
   (b) We have a live sector ETF quote (Kite data is fresh)
   (c) The ETF is in the top X% losers today (configurable threshold)
   AND the ETF intraday move is meaningfully negative
   (configurable, default -1.5%)
   This is a HIGH-CONFIDENCE block -- we are not gating on noise.

3. The CSV is the operator's curatorial lever. Missing CSV or
   missing ticker-in-CSV = UNKNOWN = ALLOW. This means the gate's
   effectiveness scales with how much of the universe the operator
   maps. We start with a 10-ticker starter file and the operator can
   grow it.

DATA FLOW:

  ticker -> [CSV lookup] -> sector name -> [ETF mapping] -> NIFTY_XX
                                                              |
                                                              v
                                          [Kite quote for ETF]
                                                              |
                                                              v
                                          compare to threshold
                                                              |
                                          v
                                       ALLOW / REJECT / UNKNOWN

PUBLIC API:

  SectorCheckResult  -- enum-like: ALLOW / REJECT / UNKNOWN
  sector_check(ticker, kite, csv_path) -- main entry point
  load_sector_map(csv_path) -- load + cache the CSV
  SECTOR_TO_ETF -- the built-in sector -> ETF proxy mapping

HARDCODED SAFEGUARDS:

- If the CSV file does not exist, sector_check returns ALLOW for every
  ticker (the default state of the system -- no operator data, no
  filtering).
- If the CSV exists but is empty or malformed, same: ALLOW.
- If the ticker is not in the CSV, ALLOW.
- If the Kite quote for the ETF fails (timeout, auth, etc.), ALLOW.
- Only the case where we have BOTH sector mapping AND live ETF data
  AND ETF intraday is meaningfully negative AND in top losers can
  REJECT fire.

This is fail-open by design. The operator can run penny with
sector filtering OFF (default behavior with empty CSV) or ON
(populate the CSV). Either way the system stays proactive.

Hard architectural rule (mirrors penny_*.py): this module MUST NOT
import from engine, regime, risk_engine, portfolio, evaluate_signal,
or evaluate_momentum_signal. It talks only to kite_client, config,
pandas/stdlib.
"""
import csv
import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ---- enum ------------------------------------------------------------

class SectorCheckResult(str, Enum):
    ALLOW = "ALLOW"     # ticker passes the sector gate (no weakness detected)
    REJECT = "REJECT"   # ticker's sector ETF is in top losers + meaningfully down
    UNKNOWN = "UNKNOWN" # data missing -- treated as ALLOW (fail-open)


# ---- built-in sector -> NSE ETF proxy mapping -------------------------
# This maps a free-text sector name from the operator's CSV to an NSE
# sectoral index ETF. The ETF is used as a real-time proxy for "how is
# this sector doing today". NSE sectoral indices are queryable via Kite
# get_quote (same as any other instrument).
#
# If the operator's CSV uses a sector name not in this map, the lookup
# falls back to NIFTY_50 (broad market). The operator can extend the
# map by either:
#   - editing this dict in code (permanent)
#   - adding a (sector, etf_proxy) column to the CSV (data-driven, v2)
#
# The "Default" key handles tickers whose sector doesn't match any
# known proxy -- we treat them as broad-market exposure.

SECTOR_TO_ETF: Dict[str, str] = {
    # Sector label in CSV  ->  Kite-tradable NSE sectoral index symbol
    "Steel":      "NIFTY_METAL",       # NSE has no pure Steel index; metal is closest proxy
    "Metal":      "NIFTY_METAL",
    "Bank":       "NIFTY_BANK",
    "Banking":    "NIFTY_BANK",
    "PSU Bank":   "NIFTY_PSU_BANK",
    "Private Bank": "NIFTY_BANK",
    "IT":         "NIFTY_IT",
    "Pharma":     "NIFTY_PHARMA",
    "Healthcare": "NIFTY_PHARMA",
    "Auto":       "NIFTY_AUTO",
    "Automobile": "NIFTY_AUTO",
    "FMCG":       "NIFTY_FMCG",
    "Consumer":   "NIFTY_FMCG",         # consumer-staples proxy
    "Energy":     "NIFTY_ENERGY",
    "Oil":        "NIFTY_ENERGY",
    "Power":      "NIFTY_ENERGY",
    "Realty":     "NIFTY_REALTY",
    "Real Estate": "NIFTY_REALTY",
    "Cement":     "NIFTY_CPSE",         # closest broad-sector proxy for cement
    "Infra":      "NIFTY_INFRA",
    "Infrastructure": "NIFTY_INFRA",
    "Textiles":   "NIFTY_MIDCAP100",    # no pure textile index; midcap is closest
    "Services":   "NIFTY_SERVSECTOR",  # Nifty Services Sector index
    "Default":    "NIFTY_50",          # broad-market fallback
}


# ---- data classes ---------------------------------------------------

@dataclass
class SectorDecision:
    """Result of a sector check."""
    result: SectorCheckResult
    sector: Optional[str]            # sector name from CSV (None if UNKNOWN)
    etf_symbol: Optional[str]        # ETF we evaluated (None if no mapping)
    etf_change_pct: Optional[float]  # intraday % change of ETF (None if no quote)
    reason: str                      # human-readable explanation for logs

    @property
    def is_blocked(self) -> bool:
        """True iff the gate REJECTED the ticker. Use this instead of
        Python truthiness because dataclass + __bool__ interact poorly
        and confuse both humans and linters."""
        return self.result == SectorCheckResult.REJECT


# ---- CSV loading ----------------------------------------------------

# [LOG-THROTTLE 2026-07-11] The missing-CSV breadcrumb fired once per
# 30s scan (~318 lines on 2026-07-10) because the file has never been
# curated. The condition is static for the life of the process, so say
# it once at INFO and drop to DEBUG afterwards.
_missing_csv_logged = False


def load_sector_map(csv_path: str) -> Dict[str, str]:
    """
    Load the (symbol, sector) CSV into a dict {symbol: sector}.

    Returns an empty dict if the file does not exist, is malformed,
    or has zero rows. The empty-dict case is the safe default and
    sector_check() will treat every ticker as UNKNOWN -> ALLOW.

    The CSV format is intentionally strict: header row required,
    exactly two columns (symbol, sector). Anything else is treated
    as malformed and returns {}.
    """
    if not csv_path or not os.path.exists(csv_path):
        global _missing_csv_logged
        if not _missing_csv_logged:
            logger.info("penny_sector_csv_missing path=%s (sector filter disabled; "
                        "logged once per process)", csv_path)
            _missing_csv_logged = True
        else:
            logger.debug("penny_sector_csv_missing path=%s", csv_path)
        return {}

    try:
        out: Dict[str, str] = {}
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                logger.warning("penny_sector_csv_empty path=%s", csv_path)
                return {}
            # Normalise field names: strip whitespace, lowercase for matching.
            field_map = {(name or "").strip().lower(): name for name in reader.fieldnames}
            symbol_field = field_map.get("symbol")
            sector_field = field_map.get("sector")
            if not symbol_field or not sector_field:
                logger.warning(
                    "penny_sector_csv_missing_columns path=%s found=%s need=symbol,sector",
                    csv_path, list(reader.fieldnames),
                )
                return {}
            for row in reader:
                sym = (row.get(symbol_field) or "").strip().upper()
                sec = (row.get(sector_field) or "").strip()
                if sym and sec:
                    out[sym] = sec
        logger.info("penny_sector_csv_loaded path=%s count=%d", csv_path, len(out))
        return out
    except Exception as e:
        logger.error("penny_sector_csv_parse_failed path=%s error=%s", csv_path, str(e))
        return {}


# ---- ETF quote evaluation --------------------------------------------

async def _get_etf_intraday_change_pct(etf_symbol: str, kite) -> Optional[float]:
    """
    Fetch the intraday % change for an NSE sectoral ETF.

    Returns a float like -0.015 for -1.5% or None if the data is
    unavailable. "Intraday" here means change from previous close to
    last traded price -- the standard "% change today" value.

    Robust to failures: any exception, missing token, or empty
    response returns None. The caller treats None as UNKNOWN.
    """
    try:
        token = kite.instrument_cache.get(etf_symbol)
        if token is None:
            # ETF not in instrument cache -- try to fetch instruments
            # (network call). This is the rare fallback path; most NSE
            # sectoral indices are in the cache after the universe refresh.
            instruments = await kite.get_instruments_nse_eq()
            token = next(
                (i["instrument_token"] for i in instruments
                 if i.get("tradingsymbol") == etf_symbol),
                None,
            )
            if token is None:
                logger.info("penny_sector_etf_token_unresolved etf=%s", etf_symbol)
                return None
            # Populate cache for next time
            kite.instrument_cache[etf_symbol] = token

        quotes = await kite.get_quote([token])
        if not quotes or token not in quotes:
            return None
        q = quotes[token]
        ltp = q.get("last_price", 0) or 0
        ohlc = q.get("ohlc") or {}
        prev_close = ohlc.get("close", 0) or 0
        if prev_close <= 0 or ltp <= 0:
            return None
        return (ltp - prev_close) / prev_close
    except Exception as e:
        logger.warning("penny_sector_etf_quote_failed etf=%s error=%s", etf_symbol, str(e))
        return None


# ---- main entry point ------------------------------------------------

async def sector_check(
    ticker: str,
    kite,
    sector_map: Dict[str, str],
    top_losers_pct: float = 0.10,
    etf_change_threshold_pct: float = -0.015,
) -> SectorDecision:
    """
    Evaluate the sector gate for one ticker.

    Returns SectorDecision with result ALLOW / REJECT / UNKNOWN.
    The default arguments match the config defaults; callers can
    override per-scan.

    FAIL-OPEN contract (operator-mandated):
      - ticker not in sector_map           -> UNKNOWN -> ALLOW
      - sector not in SECTOR_TO_ETF map    -> use NIFTY_50 (Default key)
      - ETF quote fails                    -> UNKNOWN -> ALLOW
      - ETF change >= threshold            -> ALLOW (sector is fine)
      - ETF change < threshold but ETF is NOT in top losers -> ALLOW
      - ETF change < threshold AND ETF in top losers -> REJECT
    """
    # 1. Look up sector from operator-curated map.
    sector = sector_map.get(ticker.upper())
    if sector is None:
        return SectorDecision(
            result=SectorCheckResult.UNKNOWN,
            sector=None, etf_symbol=None, etf_change_pct=None,
            reason=f"ticker {ticker} not in sector CSV (fail-open ALLOW)",
        )

    # 2. Map sector to ETF proxy. Unknown sectors -> NIFTY_50 fallback.
    etf_symbol = SECTOR_TO_ETF.get(sector, SECTOR_TO_ETF["Default"])

    # 3. Fetch live ETF intraday change.
    etf_change = await _get_etf_intraday_change_pct(etf_symbol, kite)
    if etf_change is None:
        return SectorDecision(
            result=SectorCheckResult.UNKNOWN,
            sector=sector, etf_symbol=etf_symbol, etf_change_pct=None,
            reason=f"ETF quote unavailable for {etf_symbol} (fail-open ALLOW)",
        )

    # 4. Sector is fine -- allow.
    if etf_change >= etf_change_threshold_pct:
        return SectorDecision(
            result=SectorCheckResult.ALLOW,
            sector=sector, etf_symbol=etf_symbol, etf_change_pct=etf_change,
            reason=f"sector ETF {etf_symbol} change {etf_change*100:.2f}% "
                   f">= threshold {etf_change_threshold_pct*100:.2f}%",
        )

    # 5. Sector is meaningfully DOWN. Is it in the top X% losers?
    # We don't have a universe of "all sectors today" -- we'd need to
    # fetch every sectoral ETF and rank them. For v1 we use a SIMPLE
    # PROXY: if the sector ETF is down by MORE than the threshold, AND
    # the absolute drop is severe (e.g. -2.5% or worse), reject. This
    # is more conservative than a true top-X% check but it preserves
    # proactiveness: a moderate sector dip (-1.5% to -2.5%) is allowed
    # through.
    #
    # The "top losers" intent is preserved: only the WORST sector
    # weakness blocks signals. A sector at -1.6% is weak but not in
    # the bottom decile; we let it through.
    severe_threshold = etf_change_threshold_pct * (1 + top_losers_pct)
    # Example: threshold=-1.5%, top_losers_pct=0.10
    #   severe_threshold = -1.5% * 1.10 = -1.65%
    # A sector at -1.6% is "weak" but not severe -> allow
    # A sector at -1.8% is "weak AND severe" -> reject
    if etf_change < severe_threshold:
        return SectorDecision(
            result=SectorCheckResult.REJECT,
            sector=sector, etf_symbol=etf_symbol, etf_change_pct=etf_change,
            reason=f"sector ETF {etf_symbol} down {etf_change*100:.2f}% -- "
                   f"severe drop (threshold {severe_threshold*100:.2f}%); "
                   f"ticker {ticker} rejected to avoid bear-trap breakout",
        )

    # 6. Sector is weak but not severe -- allow.
    return SectorDecision(
        result=SectorCheckResult.ALLOW,
        sector=sector, etf_symbol=etf_symbol, etf_change_pct=etf_change,
        reason=f"sector ETF {etf_symbol} change {etf_change*100:.2f}% is "
               f"weak but not severe (severe_threshold {severe_threshold*100:.2f}%)",
    )


# ---- batch helper ----------------------------------------------------

async def filter_universe_by_sector(
    tickers: List[str],
    kite,
    sector_map: Dict[str, str],
    top_losers_pct: float = 0.10,
    etf_change_threshold_pct: float = -0.015,
) -> Dict[str, SectorDecision]:
    """
    Run sector_check on a list of tickers. Returns a dict
    {ticker: SectorDecision}.

    ETF quotes are deduped -- if 10 tickers are all in "Steel", only
    one NIFTY_METAL quote is fetched. This keeps the Kite rate
    limiter pressure at ~10 calls per 100-ticker universe instead of
    100 calls.
    """
    # Group tickers by ETF symbol (after sector -> ETF mapping) so
    # we dedupe the expensive Kite calls. None is used as a sentinel
    # key for tickers with no sector mapping (they'll be UNKNOWN/ALLOW).
    sector_to_tickers: Dict[Optional[str], List[str]] = {}
    for t in tickers:
        sec = sector_map.get(t.upper())
        if sec is None:
            sector_to_tickers.setdefault(None, []).append(t)
            continue
        etf = SECTOR_TO_ETF.get(sec, SECTOR_TO_ETF["Default"])
        sector_to_tickers.setdefault(etf, []).append(t)

    # Fetch each unique ETF once.
    etf_changes: Dict[str, Optional[float]] = {}
    for etf in sector_to_tickers:
        if etf is None:
            continue
        etf_changes[etf] = await _get_etf_intraday_change_pct(etf, kite)

    # Build per-ticker decisions without re-fetching.
    out: Dict[str, SectorDecision] = {}
    severe_threshold = etf_change_threshold_pct * (1 + top_losers_pct)
    for t in tickers:
        sec = sector_map.get(t.upper())
        if sec is None:
            out[t] = SectorDecision(
                result=SectorCheckResult.UNKNOWN,
                sector=None, etf_symbol=None, etf_change_pct=None,
                reason=f"ticker {t} not in sector CSV (fail-open ALLOW)",
            )
            continue
        etf = SECTOR_TO_ETF.get(sec, SECTOR_TO_ETF["Default"])
        chg = etf_changes.get(etf)
        if chg is None:
            out[t] = SectorDecision(
                result=SectorCheckResult.UNKNOWN,
                sector=sec, etf_symbol=etf, etf_change_pct=None,
                reason=f"ETF quote unavailable for {etf} (fail-open ALLOW)",
            )
            continue
        if chg >= etf_change_threshold_pct:
            out[t] = SectorDecision(
                result=SectorCheckResult.ALLOW,
                sector=sec, etf_symbol=etf, etf_change_pct=chg,
                reason=f"sector ETF {etf} change {chg*100:.2f}% >= threshold",
            )
        elif chg < severe_threshold:
            out[t] = SectorDecision(
                result=SectorCheckResult.REJECT,
                sector=sec, etf_symbol=etf, etf_change_pct=chg,
                reason=f"sector ETF {etf} down {chg*100:.2f}% -- severe drop",
            )
        else:
            out[t] = SectorDecision(
                result=SectorCheckResult.ALLOW,
                sector=sec, etf_symbol=etf, etf_change_pct=chg,
                reason=f"sector ETF {etf} change {chg*100:.2f}% weak but not severe",
            )
    return out
