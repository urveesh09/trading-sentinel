"""
[PENNY-HEATMAP 2026-06-25] Real-time position heat-map for the penny subsystem.

WHAT IT DOES:
  Every N minutes, scan all open penny positions, fetch their live
  price via Kite, compute per-position P&L %, group by sector, and
  emit one Telegram message:

    Penny heat-map (15:42 IST) - 4 open, deployed Rs 980
    SECTOR HEAT:
      Steel     [GOLDSTAR-SM +2.1% / BAJAJHIND -1.4%]   +0.4% avg
      Realty    [ARENTERP +0.8%]                       +0.8%
      Unmapped  [21STCENMGM -0.5% / OMFURN-ST +1.2%]  +0.4%
    WARN: ARENTERP approaching SL (-2.1% from entry, SL at -3%)

WHAT IT DOES NOT DO:
  - It does NOT make the system more profitable on average. It
    surfaces CONCENTRATION RISK and BLEED so the operator can act.
  - It does NOT trigger exits. Exits are owned by the SL-M at the
    broker + the 14:30 smart-EOD + the 15:00 force-close.
  - It does NOT replace the hourly report. Hourly = closed positions
    + rejects breakdown. Heatmap = OPEN positions + live P&L drift.

DESIGN PRINCIPLES (operator-mandated 2026-06-25):

1. Fail-open. If Kite is down or a price fetch fails, that position
   shows as 'price unavailable' and the rest of the report still
   fires. NEVER block the heatmap because one quote failed.

2. Sector grouping uses the operator-curated penny_sectors.csv.
   Unmapped tickers get bucketed under 'Unmapped' (not lost).

3. Per-position row shows ticker + P&L %. Sector row shows
   aggregated P&L % across the tickers in that sector.

4. WARN line: emit ONLY if any position's P&L % is within 1.0% of
   the SL. False positives waste operator attention; better to
   under-warn than over-warn.

5. Message under 1000 chars (Telegram safe).

DATA SOURCES:
  - positions table: ticker, entry_price, stop_loss_initial, shares,
    source (filtered to source='PENNY' AND status IN ('OPEN', 'CLOSED_T1'))
    [PENNY-HEATMAP-FIX 2026-07-02] Production table uses
    `stop_loss_initial` (see position_tracker.py init_positions_db
    CREATE TABLE). The previous SELECT of `stop_loss` failed with
    "no such column" 12+ times today (rule-violation recipe below).
  - kite.get_quote(): live LTP per position (batched, single Kite call)
  - penny_sectors.csv: symbol -> sector mapping
"""
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---- defaults --------------------------------------------------------

DEFAULT_SECTORS_CSV = "python-engine/data/penny_sectors.csv"


# ---- data classes ----------------------------------------------------

@dataclass
class PositionSnap:
    """One open penny position with its current live state."""
    ticker: str
    entry_price: float
    stop_loss: float
    shares: int
    current_price: Optional[float] = None   # None if Kite quote failed
    pnl_pct: Optional[float] = None         # None if current_price unavailable
    pnl_abs: Optional[float] = None          # Rs P&L (signed); None if unavailable
    sector: str = "Unmapped"
    status: str = "OPEN"
    warning: Optional[str] = None           # set if near-SL


@dataclass
class SectorBucket:
    """Per-sector aggregation."""
    sector: str
    positions: List[PositionSnap] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.positions)

    @property
    def avg_pnl_pct(self) -> Optional[float]:
        """Average P&L % across positions in this sector. None if no
        position has a live price."""
        pcts = [p.pnl_pct for p in self.positions if p.pnl_pct is not None]
        if not pcts:
            return None
        return sum(pcts) / len(pcts)

    @property
    def total_pnl_abs(self) -> float:
        """Total Rs P&L in this sector (excludes unpriced positions)."""
        return sum(p.pnl_abs for p in self.positions if p.pnl_abs is not None)


# ---- CSV loading (mirror of penny_sector_filter) --------------------

def _load_sectors(csv_path: str) -> Dict[str, str]:
    """Read (symbol, sector) CSV into {SYMBOL: sector}. Empty dict if
    missing or malformed (same fail-open posture as the rest of the
    penny subsystem)."""
    if not csv_path or not os.path.exists(csv_path):
        return {}
    try:
        import csv
        out: Dict[str, str] = {}
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = (row.get("symbol") or "").strip().upper()
                sec = (row.get("sector") or "").strip()
                if sym and sec:
                    out[sym] = sec
        return out
    except Exception as e:
        logger.warning("penny_heatmap_sector_csv_failed path=%s error=%s",
                       csv_path, str(e))
        return {}


# ---- DB read ----------------------------------------------------------

def _read_open_positions(db_path: str) -> List[dict]:
    """Read open penny positions from the positions table.

    Returns raw dicts (not PositionSnap yet) -- caller builds the
    snap objects after fetching live prices.
    """
    rows: List[dict] = []
    try:
        with sqlite3.connect(db_path) as con:
            con.row_factory = sqlite3.Row
            # [PENNY-HEATMAP-FIX 2026-07-02] Production schema is
            # `stop_loss_initial` (position_tracker.py CREATE TABLE).
            # The previous `stop_loss` reference raised
            # "no such column: stop_loss" on every heatmap tick today
            # (logged 12+ times). Aliased to `stop_loss` so the rest
            # of this module keeps using row["stop_loss"].
            cur = con.execute(
                "SELECT ticker, entry_price, stop_loss_initial AS stop_loss, "
                "       shares, status, product_type, regime_at_entry "
                "FROM positions "
                "WHERE source = 'PENNY' "
                "AND status IN ('OPEN', 'CLOSED_T1') "
                "ORDER BY entry_date ASC"
            )
            for r in cur.fetchall():
                rows.append(dict(r))
    except sqlite3.Error as e:
        logger.warning("penny_heatmap_db_query_failed error=%s", str(e))
    return rows


# ---- live price fetch ------------------------------------------------

async def _fetch_live_prices(tickers: List[str], kite) -> Dict[str, Optional[float]]:
    """Fetch live LTP for each ticker via kite.get_quote. Returns
    {ticker: ltp} with None for failed fetches (fail-open).

    Uses a SINGLE batched get_quote call (one round-trip, all tokens).
    Operator-mandated: never make N calls when 1 will do.
    """
    out: Dict[str, Optional[float]] = {t: None for t in tickers}
    if not tickers:
        return out
    try:
        # Resolve tokens in one pass.
        token_to_ticker: Dict[int, str] = {}
        for t in tickers:
            tok = kite.instrument_cache.get(t)
            if tok is not None:
                token_to_ticker[tok] = t
        if not token_to_ticker:
            return out
        quotes = await kite.get_quote(list(token_to_ticker.keys()))
        if not quotes:
            return out
        for tok, ticker in token_to_ticker.items():
            q = quotes.get(tok) if isinstance(quotes, dict) else None
            if q:
                ltp = q.get("last_price", 0) or 0
                if ltp > 0:
                    out[ticker] = float(ltp)
    except Exception as e:
        logger.warning("penny_heatmap_get_quote_failed error=%s", str(e))
    return out


# ---- compute --------------------------------------------------------

def _build_position_snap(
    row: dict,
    ltp: Optional[float],
    sectors: Dict[str, str],
    warn_pct: float = 1.0,
) -> PositionSnap:
    """Compute one PositionSnap from a raw DB row + live price + sector map.

    [AUDIT-FIX-2.5 2026-06-25] `warn_pct` parameter added (default 1.0%)
    so the threshold is configurable via PENNY_HEATMAP_WARN_PCT.
    """
    ticker = (row.get("ticker") or "").strip().upper()
    entry = float(row.get("entry_price") or 0.0)
    sl = float(row.get("stop_loss") or 0.0)
    shares = int(row.get("shares") or 0)
    snap = PositionSnap(
        ticker=ticker,
        entry_price=entry,
        stop_loss=sl,
        shares=shares,
        current_price=ltp,
        status=row.get("status") or "OPEN",
        sector=sectors.get(ticker, "Unmapped"),
    )
    # Compute P&L % and Rs. If entry is 0 (shouldn't happen) skip.
    if ltp is not None and entry > 0:
        snap.pnl_pct = round((ltp - entry) / entry * 100, 2)
        snap.pnl_abs = round((ltp - entry) * shares, 2)
        # [AUDIT-FIX-2.5] WARN if position is within `warn_pct` of SL
        # (configurable via PENNY_HEATMAP_WARN_PCT). Previously hardcoded
        # 1.0%; now operator-tuned.
        #
        # Note: we use strict `<` rather than `<=` to avoid a
        # floating-point edge case where (ltp - sl)/entry*100 evaluates
        # to something like 1.5000000000000003 (FP error), which is >
        # the threshold 1.5 even though the "true" distance is exactly
        # 1.5. Strict `<` means the threshold is the *exclusive*
        # boundary -- a distance of exactly 1.5% does NOT warn, 1.4999%
        # does. Operator-tuned values are coarse enough that this is
        # fine. If sub-percent precision matters, use a slightly
        # larger threshold (e.g. 2.0).
        if sl > 0:
            dist_to_sl_pct = (ltp - sl) / entry * 100
            if 0 < dist_to_sl_pct < warn_pct:
                snap.warning = (
                    f"{ticker} approaching SL ({snap.pnl_pct:+.1f}% from entry, "
                    f"SL at {((sl-entry)/entry*100):+.1f}%)"
                )
    return snap


def _bucket_by_sector(positions: List[PositionSnap]) -> Dict[str, SectorBucket]:
    """Group positions by sector. Stable insertion order: by sector name
    (alphabetical) so the report is deterministic across scans."""
    out: Dict[str, SectorBucket] = {}
    for p in positions:
        out.setdefault(p.sector, SectorBucket(sector=p.sector)).positions.append(p)
    # Sort each bucket's positions by ticker (deterministic).
    for bucket in out.values():
        bucket.positions.sort(key=lambda x: x.ticker)
    return out


# ---- main builder ----------------------------------------------------

async def build_heatmap(
    db_path: str,
    kite,
    sectors_csv_path: str = DEFAULT_SECTORS_CSV,
    near_sl_warn_pct: float = 1.0,
    warn_pct_is_fraction: bool = False,
) -> Tuple[str, Dict[str, SectorBucket], int, int]:
    """Build the heatmap Telegram body. Returns (body, buckets, total_open, priced_count).

    The body is a multi-line string ready for sendMessage. The buckets
    are returned for testing + downstream consumers (e.g. the dashboard).
    total_open = positions read; priced_count = how many got a live LTP.

    Args:
      near_sl_warn_pct: distance from stop_loss (as %) at which to
        surface a WARN line.
      warn_pct_is_fraction: if True, near_sl_warn_pct is treated as a
        fraction (0.01 = 1%); if False (default), as percent (1.0 = 1%).
        [AUDIT-FIX-2.5 2026-06-25] The caller now passes a fraction from
        config.PENNY_HEATMAP_WARN_PCT, so warn_pct_is_fraction=True.
        The default of False keeps back-compat with the original 1.0=1%.
    """
    raw_rows = _read_open_positions(db_path)
    if not raw_rows:
        return ("Penny heat-map: 0 open positions.", {}, 0, 0)

    tickers = [(row.get("ticker") or "").strip().upper() for row in raw_rows]
    live_prices = await _fetch_live_prices(tickers, kite)

    sectors = _load_sectors(sectors_csv_path)

    # [AUDIT-FIX-2.5] Normalize the warn threshold to percent (the
    # _build_position_snap comparison is in percent). If the caller
    # passed a fraction, multiply by 100.
    warn_pct = near_sl_warn_pct if warn_pct_is_fraction is False else near_sl_warn_pct * 100

    snaps: List[PositionSnap] = []
    for row in raw_rows:
        ticker = (row.get("ticker") or "").strip().upper()
        snap = _build_position_snap(row, live_prices.get(ticker), sectors, warn_pct=warn_pct)
        snaps.append(snap)

    buckets = _bucket_by_sector(snaps)
    priced_count = sum(1 for s in snaps if s.current_price is not None)

    body = _format_body(buckets, len(snaps), priced_count)
    return (body, buckets, len(snaps), priced_count)


def _format_body(
    buckets: Dict[str, SectorBucket],
    total_open: int,
    priced_count: int,
) -> str:
    """Format the multi-line heatmap body."""
    now_ist = datetime.now(timezone.utc).astimezone()
    # Use a simple HH:MM IST stamp (UTC+5:30 or +5:45 -- we approximate
    # with UTC+5:30 here since we don't want a tz dependency in tests).
    hh = (now_ist.hour) % 24
    mm = now_ist.minute
    timestamp = f"{hh:02d}:{mm:02d} IST"

    lines = [f"Penny heat-map ({timestamp}) - {total_open} open, {priced_count} priced"]

    # Sort sectors alphabetically for determinism (Unmapped last).
    sorted_sectors = sorted(buckets.keys(), key=lambda s: (s == "Unmapped", s))
    for sector in sorted_sectors:
        bucket = buckets[sector]
        # Per-position breakdown
        per_pos = " / ".join(
            f"{p.ticker} {p.pnl_pct:+.1f}%"
            if p.pnl_pct is not None else f"{p.ticker} n/a"
            for p in bucket.positions
        )
        # Average
        avg = bucket.avg_pnl_pct
        avg_str = f"{avg:+.2f}% avg" if avg is not None else "no live prices"
        lines.append(f"  {sector:12s} [{per_pos}]   {avg_str}")

    # WARN lines (only if any position is near SL)
    warns = [p.warning for p in snaps_with_warnings(buckets)]
    for w in warns:
        lines.append(f"WARN: {w}")

    return "\n".join(lines)


def snaps_with_warnings(buckets: Dict[str, SectorBucket]) -> List[PositionSnap]:
    """Flatten bucket.positions and filter to those with warnings set."""
    out: List[PositionSnap] = []
    for bucket in buckets.values():
        for p in bucket.positions:
            if p.warning:
                out.append(p)
    return out
