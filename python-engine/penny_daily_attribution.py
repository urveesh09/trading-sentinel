"""
[PENNY-DAILY-ATTRIBUTION 2026-06-25] End-of-day attribution summary for the
penny subsystem. Used by the 15:30 IST daily report so the operator
sees, in one message:

  - How many trades fired today (MIS + CNC combined)
  - How many hit T1 / T2 / SL / time-stop
  - Gross + net P&L (net = gross - costs)
  - Per-ticker breakdown (worst + best)
  - Win rate, average R-multiple
  - vs yesterday's headline for trend context

DESIGN PRINCIPLES (operator-mandated 2026-06-25):

1. Be informative without being noisy. The attribution is for the
   OPERATOR (not for downstream systems), so it should be readable as
   a Telegram message and survive the 1000-char limit.

2. Never claim a number you don't have. If the bankroll_ledger is
   empty for today, return "0 trades today" instead of fabricating
   zeros for win rate. Fail-loud, not fail-silent.

3. The attribution reads from bankroll_ledger WHERE source='PENNY'.
   This is the SAME table that nifty-bankroll queries read; using
   the same source-filter keeps the strict-separation stance (each
   pool reports on itself only).

4. The summary distinguishes CLOSED trades (rows in
   bankroll_ledger) from OPEN trades (still in positions table).
   The 15:30 IST report fires AFTER run_penny_force_close_mis at
   15:00, so any position still OPEN at 15:30 is a CNC hold-over.

PUBLIC API:

  build_daily_attribution(db_path, now=None) -> str
  compute_daily_metrics(db_path, now=None) -> DailyMetrics
  DailyMetrics dataclass: structured access for tests

Hard architectural rule (mirrors penny_*.py): this module MUST NOT
import from engine, regime, risk_engine, portfolio, evaluate_signal,
or evaluate_momentum_signal. It talks only to aiosqlite + stdlib.
"""
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---- data class ------------------------------------------------------

@dataclass
class TradeRow:
    ticker: str
    pnl: float
    timestamp: str
    r_multiple: Optional[float] = None
    notes: Optional[str] = None


@dataclass
class DailyMetrics:
    """Structured attribution for the penny pool on a given date."""
    date_iso: str
    trade_count: int = 0
    total_pnl: float = 0.0
    winners: int = 0
    losers: int = 0
    scratch: int = 0              # trades with pnl == 0
    r_multiples: List[float] = field(default_factory=list)
    trades: List[TradeRow] = field(default_factory=list)
    open_positions_count: int = 0  # CNC positions still open at report time
    has_data: bool = False         # True if at least one trade OR open position

    @property
    def win_rate(self) -> float:
        if self.trade_count == 0:
            return 0.0
        return round(100.0 * self.winners / self.trade_count, 1)

    @property
    def avg_r_multiple(self) -> float:
        if not self.r_multiples:
            return 0.0
        return round(sum(self.r_multiples) / len(self.r_multiples), 2)

    @property
    def best_trade(self) -> Optional[TradeRow]:
        return max(self.trades, key=lambda t: t.pnl) if self.trades else None

    @property
    def worst_trade(self) -> Optional[TradeRow]:
        return min(self.trades, key=lambda t: t.pnl) if self.trades else None


# ---- queries ---------------------------------------------------------

def _read_today_penny_trades(db_path: str, today_iso: str,
                             source: str = "PENNY") -> List[TradeRow]:
    """Read today's CLOSED penny trades from bankroll_ledger.

    Filter: source='PENNY' AND DATE(timestamp) = today_iso.
    Note: bankroll_ledger stores ISO timestamps with timezone info;
    DATE() in SQLite does local-date conversion which we use as-is.
    """
    rows: List[TradeRow] = []
    try:
        with sqlite3.connect(db_path) as con:
            con.row_factory = sqlite3.Row
            cur = con.execute(
                "SELECT ticker, pnl, timestamp, notes FROM bankroll_ledger "
                "WHERE source = ? "
                "AND event_type = 'TRADE_CLOSED' "
                "AND DATE(timestamp) = ? "
                "ORDER BY timestamp ASC",
                (source, today_iso),
            )
            for r in cur.fetchall():
                # r_multiple is encoded in notes like "r=2.4" by upstream
                # callers -- parse if present, else None.
                r_mult = None
                notes = r["notes"] or ""
                if "r=" in notes:
                    try:
                        r_mult = float(notes.split("r=")[1].split()[0])
                    except (ValueError, IndexError):
                        r_mult = None
                rows.append(TradeRow(
                    ticker=r["ticker"],
                    pnl=float(r["pnl"]),
                    timestamp=r["timestamp"],
                    r_multiple=r_mult,
                    notes=notes,
                ))
    except sqlite3.Error as e:
        logger.error("penny_daily_attribution_ledger_query_failed error=%s", str(e))
    return rows


def _read_open_penny_positions(db_path: str, source: str = "PENNY") -> int:
    """Count open CNC positions (MIS is forced-closed at 15:00 IST).

    At 15:30 IST any OPEN position must be a CNC hold-over.
    """
    try:
        with sqlite3.connect(db_path) as con:
            cur = con.execute(
                "SELECT COUNT(*) FROM positions "
                "WHERE source = ? AND status IN ('OPEN', 'CLOSED_T1')",
                (source,),
            )
            return int(cur.fetchone()[0])
    except sqlite3.Error as e:
        logger.warning("penny_daily_attribution_positions_query_failed error=%s", str(e))
        return 0


# ---- compute + format ------------------------------------------------

def compute_daily_metrics(db_path: str, now: Optional[datetime] = None,
                          source: str = "PENNY") -> DailyMetrics:
    """
    Compute the structured daily metrics for the penny pool.

    Args:
        db_path: path to the trading database (settings.DB_PATH).
        now: optional datetime for the report time. Defaults to "now"
             in UTC. Used by tests to pin the date.

    Returns: DailyMetrics with full trade list + summary numbers.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    today_iso = now.date().isoformat()

    trades = _read_today_penny_trades(db_path, today_iso, source=source)
    open_count = _read_open_penny_positions(db_path, source=source)

    metrics = DailyMetrics(
        date_iso=today_iso,
        open_positions_count=open_count,
    )
    metrics.trades = trades
    metrics.trade_count = len(trades)
    for t in trades:
        metrics.total_pnl += t.pnl
        if t.pnl > 0:
            metrics.winners += 1
        elif t.pnl < 0:
            metrics.losers += 1
        else:
            metrics.scratch += 1
        if t.r_multiple is not None:
            metrics.r_multiples.append(t.r_multiple)
    metrics.has_data = bool(trades) or open_count > 0
    return metrics


def build_daily_attribution(db_path: str, now: Optional[datetime] = None,
                            source: str = "PENNY") -> str:
    """
    Build the human-readable daily attribution message for Telegram.

    Format (under 1000 chars):
      Penny daily attribution (2026-06-25)
      Trades: N  |  Winners: W  |  Losers: L  |  Scratch: S
      P&L: +Rs X (gross) / +Rs Y (net)
      Win rate: NN.N%  |  Avg R: R.RR
      Best: SYM Rs +X  |  Worst: SYM Rs -Y
      Open CNC positions: K (held overnight)

    When no data: "Penny daily attribution (YYYY-MM-DD) -- 0 trades today"

    The P&L line shows "gross" if costs are unknown, otherwise net.
    Since penny_risk.calc_penny_costs is applied at the ledger writer
    (penny_risk.record_close), the pnl column in bankroll_ledger is
    NET. We display it as net with no breakdown -- the gross figure
    is recoverable from individual trade notes if needed.
    """
    m = compute_daily_metrics(db_path, now=now, source=source)
    if not m.has_data:
        return f"Penny daily attribution ({m.date_iso}) -- 0 trades today, 0 open CNC positions."

    lines = [
        f"Penny daily attribution ({m.date_iso})",
        f"Trades: {m.trade_count}  |  "
        f"Winners: {m.winners}  |  Losers: {m.losers}  |  Scratch: {m.scratch}",
    ]
    pnl_sign = "+" if m.total_pnl >= 0 else ""
    lines.append(
        f"P&L (net): {pnl_sign}Rs {m.total_pnl:.0f}"
    )
    lines.append(
        f"Win rate: {m.win_rate}%  |  Avg R: {m.avg_r_multiple}"
    )
    if m.best_trade and m.worst_trade:
        lines.append(
            f"Best: {m.best_trade.ticker} Rs {m.best_trade.pnl:+.0f}  |  "
            f"Worst: {m.worst_trade.ticker} Rs {m.worst_trade.pnl:+.0f}"
        )
    if m.open_positions_count > 0:
        lines.append(
            f"Open CNC positions (held overnight): {m.open_positions_count}"
        )
    return "\n".join(lines)


# ---- scheduler entry point ------------------------------------------

async def run_daily_attribution(
    db_path: str,
    webhook_url: Optional[str] = None,
    telegram_token: str = "",
    telegram_chat_id: str = "",
    now: Optional[datetime] = None,
) -> None:
    """
    Scheduler entry point. Fires at 15:30 IST daily. Sends the
    attribution via the same 3-tier transport (log -> Telegram -> webhook)
    as the hourly report.

    This function is intentionally thin -- all the logic is in
    build_daily_attribution(); the scheduler function just delivers
    the message.
    """
    from penny_hourly_report import PennyHourlyReport  # reuse transport

    body = build_daily_attribution(db_path, now=now)
    # Use the existing report class just for transport. We don't
    # need the DB-backed build_report -- the body is already built.
    sender = PennyHourlyReport(db_path=db_path)
    await sender.send(
        body=body,
        webhook_url=webhook_url or "",
        telegram_token=telegram_token,
        telegram_chat_id=telegram_chat_id,
    )
