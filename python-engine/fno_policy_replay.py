"""Full-policy single-leg F&O replay over archived quotes (research only).

The replay re-runs the *shipped* NIFTY single-leg paper book tick by tick on
evidence the live system actually had:

* futures 5-minute candles (``fut_candles``) for the day's front future,
* every archived NIFTY quote batch (front future + ATM±5 calls/puts for two
  expiries, raw provider packets verified by ``verify_archive_event``),
* the live ``fno_signals`` regime per bar (point-in-time, never re-derived).

Decisions call the production code: ``evaluate_fno_mom`` (signal),
``fno_chain._parse_quote_entry`` + ``ChainSnapshot`` (chain view),
``fno_entry_plan.plan_single_leg_entry`` (strike, gates, sizing, max loss,
reward/risk), ``evaluate_single_leg_exit`` (exit ladder), ``calc_fno_costs``,
``fno_shared_risk.entry_halts`` (loss brakes) and
``fno_adaptive_risk.risk_stance`` (size multiplier and two-strike day halt,
read from the same completed-trade evidence the live tick reads). Paper fills follow the
executor: buy at the ask, sell at the bid (else LTP).

Clock: the live tick runs every 90 s. BASELINE processes the first archived
quote batch at or after each 90-second grid point, phase-aligned to that day's
logged live evaluations (``live_tick_phase``); a candidate may
manage open positions on every batch (~60 s, the archive's resolution — true
tick-level speed cannot be measured from this data). Exits run before entries.

Pool: the live pool is FNO_PAPER equity (allocation + realised P&L of both
paper books). The replay seeds equity with every close before the window and
adds the defined-risk book's actual historical closes at their close times,
identically for every arm; the single-leg book's cash is the replay's own.

Not replayed: the defined-risk book's decisions, shared-risk reservations
across books, broker rejections and scheduler jitter. A held contract that
drifts outside the archived ATM±5 window has no quote; it cannot be priced
(as live would refuse an unpriced exit) and is reported.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import sqlite3
from typing import Optional

import pandas as pd
import pytz

IST = pytz.timezone("Asia/Kolkata")
GRID_SECONDS = 90
SESSION_START = time(9, 15)
RVOL_FETCH_CALENDAR_DAYS = 21      # fno_orchestrator.RVOL_FETCH_CALENDAR_DAYS
MAX_QUOTE_AGE_SECONDS = 300        # archive event usability (not a gate)


class FnoReplayError(RuntimeError):
    pass


# ---- policy (baseline + declared candidates) ------------------------------

@dataclass(frozen=True)
class ReplayPolicy:
    """Arm definition. BASELINE leaves every switch off."""
    name: str = "BASELINE"
    manage_every_observation: bool = False   # FAST_EXIT: ~60 s management
    partial_at_target: bool = False          # bank half (when >=2 lots) as the target arms the trail
    pyramid_house_money: bool = False        # add one lot after target only if locked profit covers its risk
    trend_day_filter: bool = False           # enter only on compressed-opening-range days
    trend_day_lookback: int = 10
    exit_overrides: tuple = ()               # ((setting, value), ...) applied to the exit ladder params
    reentry_confirmation: Optional[bool] = None   # None = live setting


POLICIES = {
    "BASELINE": ReplayPolicy(),
    "FNO_FAST_EXIT": ReplayPolicy(name="FNO_FAST_EXIT", manage_every_observation=True),
    "FNO_PARTIAL_TRAIL": ReplayPolicy(name="FNO_PARTIAL_TRAIL", partial_at_target=True),
    "FNO_HOUSE_MONEY_PYRAMID": ReplayPolicy(name="FNO_HOUSE_MONEY_PYRAMID", pyramid_house_money=True),
    "FNO_TREND_DAY": ReplayPolicy(name="FNO_TREND_DAY", trend_day_filter=True),
    "FNO_TRADER_V1": ReplayPolicy(name="FNO_TRADER_V1", manage_every_observation=True, partial_at_target=True,
                                  pyramid_house_money=True, trend_day_filter=True),
}


# ---- data ------------------------------------------------------------------

@dataclass(frozen=True)
class Observation:
    """One archived NIFTY quote batch."""
    at: datetime                                   # IST receipt clock
    future: object                                 # ContractQuote of the front future
    options: dict                                  # token -> ContractQuote
    expiries: tuple                                # option expiries present, ascending


class ReplayData:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        self.db = self.root / "fno-replay.sqlite"
        if not self.db.is_file():
            raise FnoReplayError(f"missing {self.db}")
        self._regimes: Optional[dict[str, str]] = None

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(f"file:{self.db.resolve().as_posix()}?mode=ro", uri=True)

    @property
    def days(self) -> list[str]:
        return list(self.manifest["quote_days"])

    def observations(self, day: str) -> tuple[list[Observation], Counter]:
        """Verified NIFTY batches for one session, ascending by receipt."""
        from fno_chain import _parse_quote_entry
        from fno_exit_experiment import verify_archive_event
        from fno_models import Contract
        from intraday_spread_archive_adapter import read_archived_quote_events

        batches: dict[str, list[dict]] = defaultdict(list)
        for event in read_archived_quote_events(self.root, days=[day]):
            contract = event.get("contract") or {}
            if contract.get("underlying") == "NIFTY":
                batches[event["received_at_utc"]].append(event)
        excluded: Counter = Counter()
        out: list[Observation] = []
        for received in sorted(batches):
            future, options = None, {}
            for event in batches[received]:
                spec = event["contract"]
                token = int(spec["instrument_token"])
                verified, reason = verify_archive_event(event, token=token, symbol=spec["tradingsymbol"],
                                                        max_age_seconds=MAX_QUOTE_AGE_SECONDS)
                if verified is None:
                    excluded[reason] += 1
                    continue
                contract = Contract(token=token, tradingsymbol=spec["tradingsymbol"], name="NIFTY",
                                    expiry=date.fromisoformat(spec["expiry"]), strike=float(spec["strike"]),
                                    instrument_type=spec["instrument_type"], lot_size=int(spec["lot_size"]),
                                    tick_size=float(spec["tick_size"]))
                quote = _parse_quote_entry(contract, event["raw_packet"])
                if spec["instrument_type"] == "FUT":
                    future = quote
                else:
                    options[token] = quote
            if future is None or future.ltp <= 0:
                excluded["batch_without_future"] += 1
                continue
            at = datetime.fromisoformat(received.replace("Z", "+00:00")).astimezone(IST)
            expiries = tuple(sorted({q.contract.expiry for q in options.values()}))
            out.append(Observation(at, future, options, expiries))
        return out, excluded

    def futures_frame(self, token: int, day: date) -> pd.DataFrame:
        """The live 21-calendar-day 5-minute history window for ``token``."""
        start = (day - timedelta(days=RVOL_FETCH_CALENDAR_DAYS)).isoformat()
        with self._connect() as con:
            rows = con.execute(
                "SELECT datetime, open, high, low, close, volume FROM fut_candles WHERE instrument_token=? "
                "AND interval='5minute' AND datetime>=? AND datetime<? ORDER BY datetime",
                (int(token), start, (day + timedelta(days=1)).isoformat())).fetchall()
        frame = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume"])
        frame.index = pd.to_datetime(frame.pop("datetime"))
        return frame

    def regime(self, bar_ts: str, day: str) -> tuple[str, str]:
        """Live regime logged for this bar, else the latest earlier the same day."""
        if self._regimes is None:
            with self._connect() as con:
                self._regimes = {row[0]: row[1] for row in con.execute(
                    "SELECT bar_ts, regime FROM fno_signals WHERE regime IS NOT NULL AND regime!='' "
                    "ORDER BY evaluated_at")}
        if bar_ts in self._regimes:
            return self._regimes[bar_ts], "logged_for_bar"
        earlier = [key for key in self._regimes if key.startswith(day) and key < bar_ts]
        if earlier:
            return self._regimes[max(earlier)], "logged_earlier_same_day"
        return "UNKNOWN", "not_logged"

    def live_tick_phase(self, day: str) -> Optional[float]:
        """Seconds after 09:15 (mod the 90 s cadence) of the live scheduler that day.

        The live tick runs on a free 90-second interval whose phase depends on
        process start; its evaluations are logged with ``evaluated_at``. Aligning
        the replay grid to that phase removes up-to-a-minute quote timing drift.
        """
        with self._connect() as con:
            row = con.execute("SELECT MIN(evaluated_at) FROM fno_signals WHERE bar_ts LIKE ?",
                              (f"{day}%",)).fetchone()
        if not row or not row[0]:
            return None
        first = _aware(row[0]).astimezone(IST)
        anchor = IST.localize(datetime.combine(first.date(), SESSION_START))
        return (first - anchor).total_seconds() % GRID_SECONDS

    def paper_closes(self) -> list[tuple[datetime, float, str]]:
        """(close instant, net pnl, book) for every closed FNO_PAPER position."""
        out = []
        with self._connect() as con:
            for stamp, pnl in con.execute("SELECT exit_time, pnl FROM fno_positions WHERE source='FNO_PAPER' "
                                          "AND status='CLOSED' AND exit_time IS NOT NULL"):
                out.append((_aware(stamp), float(pnl or 0.0), "SINGLE_LEG"))
            for stamp, pnl in con.execute("SELECT closed_at, pnl FROM fno_dr_positions WHERE source='FNO_PAPER' "
                                          "AND status='CLOSED' AND closed_at IS NOT NULL"):
                out.append((_aware(stamp), float(pnl or 0.0), "DEFINED_RISK"))
        return sorted(out)

    def live_single_leg(self, start: str, end: str) -> list[dict]:
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            return [dict(row) for row in con.execute(
                "SELECT tradingsymbol, lots, entry_time, entry_premium, exit_time, exit_premium, exit_reason, "
                "pnl, bar_ts FROM fno_positions WHERE source='FNO_PAPER' AND entry_date BETWEEN ? AND ? "
                "ORDER BY entry_time", (start, end))]


def _last_closed_bar(frame: pd.DataFrame, now: datetime) -> Optional[str]:
    """``MomSignal.bar_ts`` of the newest bar closed at ``now`` (same rule as the engine)."""
    naive = now.replace(tzinfo=None)
    closed = frame.index[(frame.index + timedelta(minutes=5) <= naive) & (frame.index.date == naive.date())]
    return closed[-1].strftime("%Y-%m-%d %H:%M:%S") if len(closed) else None


def _aware(stamp: str) -> datetime:
    value = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    return value if value.tzinfo else IST.localize(value)


# ---- book ------------------------------------------------------------------

@dataclass
class OpenLeg:
    """Mirror of an ``fno_positions`` row the exit ladder reads."""
    id: int
    tradingsymbol: str
    token: int
    direction: str
    lots: int
    lot_size: int
    entry_time: str
    entry_premium: float
    entry_underlying: float
    stop_underlying: float
    target_underlying: float
    premium_stop: float
    atr_at_entry: float
    delta_at_entry: float
    bar_ts: str
    trail_active: int = 0
    trail_stop_underlying: Optional[float] = None
    best_underlying: Optional[float] = None
    best_premium: Optional[float] = None
    initial_qty: int = 0
    fills: list = field(default_factory=list)       # partial / pyramid legs
    pyramided: bool = False

    @property
    def qty(self) -> int:
        return self.lots * self.lot_size


@dataclass
class Book:
    equity: float
    closes: list = field(default_factory=list)        # (instant, pnl, book)
    completed: list = field(default_factory=list)     # fno_adaptive_risk.Close, one per finished trade
    open: dict = field(default_factory=dict)          # id -> OpenLeg
    trades: list = field(default_factory=list)
    entered_bars: set = field(default_factory=set)
    entries_today: Counter = field(default_factory=Counter)
    next_id: int = 1


def _close_record(leg: OpenLeg, at: datetime, price: float, reason: str, fut: float) -> tuple[dict, float]:
    """Trade record (all legs) and the final leg's own net cash.

    Banked partials were already settled when they filled, so the caller adds
    only the returned final-leg net to equity. R is measured on the initial
    quantity's premium backstop, as the live book does.
    """
    from config import settings
    from fno_costs import calc_fno_costs
    gross = (price - leg.entry_premium) * leg.qty
    final_net = gross - calc_fno_costs(leg.entry_premium, price, leg.qty)
    total = final_net + sum(f["net_pnl"] for f in leg.fills)
    risk = leg.fills[0]["entry_premium"] if leg.fills and "entry_premium" in leg.fills[0] else leg.entry_premium
    risk_rs = risk * settings.FNO_STOP_PREMIUM_PCT * leg.initial_qty
    return ({"tradingsymbol": leg.tradingsymbol, "direction": leg.direction, "bar_ts": leg.bar_ts,
             "entry_time": leg.entry_time, "entry_premium": round(leg.entry_premium, 4),
             "lots_at_exit": leg.lots, "exit_time": at.isoformat(), "exit_premium": price,
             "exit_underlying": fut, "exit_reason": reason, "entry_underlying": leg.entry_underlying,
             "stop_underlying": leg.stop_underlying,
             "gross_pnl": round(gross + sum(f["gross_pnl"] for f in leg.fills), 4),
             "net_pnl": round(total, 4), "r_multiple": round(total / risk_rs, 4) if risk_rs > 0 else None,
             "fills": leg.fills}, final_net)


class SingleLegReplay:
    def __init__(self, data: ReplayData, policy: ReplayPolicy):
        self.data, self.policy = data, policy
        self.funnel: Counter = Counter()
        self.notes: Counter = Counter()
        self.decisions: list[dict] = []       # every fired signal and what happened to it

    # -- risk state ------------------------------------------------------
    def _halts(self, book: Book, now: datetime) -> tuple[str, ...]:
        from config import settings
        from fno_shared_risk import entry_halts, policy_from_settings
        visible = [(at, pnl, kind) for at, pnl, kind in book.closes if at <= now]
        completed = sorted(((at, pnl) for at, pnl, kind in visible if kind != "SINGLE_LEG_PARTIAL"), reverse=True)
        visible = [(at, pnl) for at, pnl, _ in visible]
        return entry_halts(trade_cash=visible, completed_newest_first=completed, today_ist=now.date(),
                           pool_rs=float(settings.FNO_PAPER_BANKROLL), equity_rs=book.equity,
                           policy=policy_from_settings()).active

    def _stance(self, book: Book, now: datetime):
        """Live sizing stance: allocation-anchored, one Close per finished trade
        (a banked partial is part of its trade, as the live row stores it)."""
        from config import settings
        from fno_adaptive_risk import policy_from_settings, risk_stance
        return risk_stance(book.completed, allocation=float(settings.FNO_PAPER_BANKROLL), now=now,
                           policy=policy_from_settings())

    def _apply_exogenous(self, book: Book, pending: list, now: datetime) -> None:
        from fno_adaptive_risk import Close
        while pending and pending[0][0] <= now:
            at, pnl, kind = pending.pop(0)
            book.equity += pnl
            book.closes.append((at, pnl, kind))
            book.completed.append(Close(at, pnl, kind == "SINGLE_LEG"))

    # -- management ------------------------------------------------------
    def _manage(self, book: Book, obs: Observation, now: datetime) -> None:
        from config import settings
        from fno_adaptive_risk import Close
        from fno_exit_rules import evaluate_single_leg_exit, live_single_leg_exit_params
        hard_flat = now.hour * 60 + now.minute >= settings.FNO_HARD_FLAT_MIN
        fut_price = obs.future.ltp
        for leg_id in sorted(book.open):
            leg = book.open[leg_id]
            quote = obs.options.get(leg.token)
            bid = quote.bid if quote else 0.0
            ltp = quote.ltp if quote else 0.0
            basis = bid if bid > 0 else ltp
            params = {**live_single_leg_exit_params(settings), **dict(self.policy.exit_overrides)}
            decision = evaluate_single_leg_exit(leg, now_ist=now, fut_price=fut_price, exit_px_basis=basis,
                                                hard_flat=hard_flat, params=params)
            leg.best_premium = decision.best_premium
            if decision.persist_trail:
                leg.trail_active = 1 if decision.trail_active else 0
                leg.trail_stop_underlying = decision.trail_stop
                leg.best_underlying = decision.best_underlying
            if decision.trail_newly_armed and not decision.exit_reason and quote is not None:
                self._on_target(book, leg, obs, now)
            if not decision.exit_reason:
                continue
            if basis <= 0:
                self.notes["exit_unpriced_no_archived_quote"] += 1
                continue
            record, final_net = _close_record(leg, now, basis, decision.exit_reason, fut_price)
            book.trades.append(record)
            book.equity += final_net
            book.closes.append((now, final_net, "SINGLE_LEG"))
            book.completed.append(Close(now, record["net_pnl"], True))
            del book.open[leg_id]

    def _on_target(self, book: Book, leg: OpenLeg, obs: Observation, now: datetime) -> None:
        """Candidate hooks fired once, when the target first arms the trail."""
        from fno_costs import calc_fno_costs
        quote = obs.options[leg.token]
        if self.policy.partial_at_target and leg.lots >= 2 and quote.bid > 0:
            sell_lots = leg.lots // 2
            qty = sell_lots * leg.lot_size
            gross = (quote.bid - leg.entry_premium) * qty
            cost = calc_fno_costs(leg.entry_premium, quote.bid, qty)
            leg.fills.append({"kind": "PARTIAL", "at": now.isoformat(), "qty": qty, "price": quote.bid,
                              "entry_premium": leg.entry_premium,
                              "gross_pnl": round(gross, 4), "net_pnl": round(gross - cost, 4)})
            book.equity += gross - cost
            book.closes.append((now, gross - cost, "SINGLE_LEG_PARTIAL"))
            leg.lots -= sell_lots
            self.notes["partial_banked"] += 1
        if self.policy.pyramid_house_money and not leg.pyramided:
            self._house_money_add(leg, quote, obs, now)

    def _house_money_add(self, leg: OpenLeg, quote, obs: Observation, now: datetime) -> None:
        """Add one lot only when the open position's locked profit at the trail
        stop covers the add-on's own loss at that stop plus its spread."""
        from config import settings
        from fno_models import Leg, OptionType
        from fno_risk import validate_position
        if leg.trail_stop_underlying is None or quote.ask <= 0 or quote.bid <= 0:
            return
        if leg.lots + 1 > settings.FNO_MAX_LOTS:
            self.notes["pyramid_skipped_max_lots"] += 1
            return
        delta = abs(leg.delta_at_entry) or 0.5
        trail_gap = abs(leg.trail_stop_underlying - leg.entry_underlying)
        favourable = (leg.trail_stop_underlying - leg.entry_underlying) * (1 if leg.direction == "LONG" else -1)
        locked = delta * favourable * leg.qty if favourable > 0 else 0.0
        add_risk = delta * abs(obs.future.ltp - leg.trail_stop_underlying) * leg.lot_size \
            + (quote.ask - quote.bid) * leg.lot_size
        if locked < add_risk or trail_gap <= 0:
            self.notes["pyramid_skipped_not_house_money"] += 1
            return
        opt_type = OptionType(leg.tradingsymbol[-2:])
        new_lots = leg.lots + 1
        new_premium = (leg.entry_premium * leg.lots + quote.ask) / new_lots
        ok, _reason, _ml = validate_position([Leg(opt_type=opt_type, strike=0.0 + quote.contract.strike,
                                                  quantity=new_lots, premium=new_premium)], leg.lot_size)
        if not ok:
            self.notes["pyramid_skipped_constitution"] += 1
            return
        leg.fills.append({"kind": "PYRAMID_ADD", "at": now.isoformat(), "qty": leg.lot_size, "price": quote.ask,
                          "entry_premium": leg.entry_premium, "gross_pnl": 0.0, "net_pnl": 0.0})
        leg.entry_premium, leg.lots, leg.pyramided = new_premium, new_lots, True
        self.notes["pyramid_added"] += 1

    # -- entry -----------------------------------------------------------
    def _trend_day_ok(self, frame: pd.DataFrame, day: date, or_high: float, or_low: float) -> bool:
        """Today's 30-minute opening range no wider than the median of prior sessions'."""
        from config import settings
        widths = []
        window_end = (datetime.combine(day, SESSION_START) + timedelta(minutes=settings.FNO_OR_MINUTES)).time()
        for session, bars in frame.groupby(frame.index.date):
            if session >= day:
                continue
            opening = bars[(bars.index.time >= SESSION_START) & (bars.index.time < window_end)]
            if len(opening) == settings.FNO_OR_MINUTES // 5:
                widths.append(float(opening["high"].max() - opening["low"].min()))
        widths = widths[-self.policy.trend_day_lookback:]
        if len(widths) < 5:
            self.notes["trend_filter_insufficient_history"] += 1
            return False
        return (or_high - or_low) <= sorted(widths)[len(widths) // 2]

    def _entry(self, book: Book, obs: Observation, frame: pd.DataFrame, day: str, now: datetime) -> None:
        from config import settings
        from fno_chain import ChainSnapshot, years_to_expiry, _parity_forward
        from fno_engine_mom import evaluate_fno_mom
        from fno_entry_plan import EntryState, plan_single_leg_entry
        minute = now.hour * 60 + now.minute
        if not (settings.FNO_ENTRY_START_MIN <= minute < settings.FNO_ENTRY_END_MIN):
            return
        today = now.date()
        bar_ts = _last_closed_bar(frame, now)
        if bar_ts is None:
            return
        regime, regime_source = self.data.regime(bar_ts, day)
        self.notes[f"regime_{regime_source}"] += 1
        sig = evaluate_fno_mom(frame, regime, now)
        if sig.direction is None:
            self.funnel[f"engine:{sig.reject_reason}"] += 1
            return
        if sig.bar_ts in book.entered_bars:
            return
        if self.policy.trend_day_filter and not self._trend_day_ok(frame, today, sig.or_high, sig.or_low):
            self.funnel["candidate:not_trend_day"] += 1
            return
        expiry = next((e for e in obs.expiries if e >= today), None)
        if expiry is None:
            self.funnel["chain_unavailable"] += 1
            return
        quotes = {(q.contract.strike, q.contract.instrument_type): q
                  for q in obs.options.values() if q.contract.expiry == expiry}
        forward = obs.future.ltp
        strikes = sorted({k for k, _ in quotes})
        atm = min(strikes, key=lambda k: abs(k - forward)) if strikes else forward
        snap = ChainSnapshot(taken_at=obs.at, expiry=expiry, forward=forward,
                             parity_forward=_parity_forward(quotes, atm, years_to_expiry(expiry, obs.at)),
                             lot_size=obs.future.contract.lot_size, fut_quote=obs.future, quotes=quotes)
        held = frozenset(leg.tradingsymbol for leg in book.open.values())
        open_premium = sum(leg.entry_premium * leg.qty for leg in book.open.values())
        stance = self._stance(book, now)
        halts = self._halts(book, now)
        if stance.single_leg_halted_today:
            halts = (*halts, f"two_strike_day_halt losses={stance.single_leg_losses_today}")
        from fno_entry_plan import REENTRY_STOP_REASONS, reentry_level
        confirm = (settings.FNO_REENTRY_REQUIRES_CONFIRMATION if self.policy.reentry_confirmation is None
                   else self.policy.reentry_confirmation)
        levels = {}
        if confirm:
            for t in sorted((t for t in book.trades if "net_pnl" in t), key=lambda t: t["exit_time"]):
                if t["exit_time"][:10] == today.isoformat() and t["exit_reason"] in REENTRY_STOP_REASONS:
                    levels[t["direction"]] = reentry_level(t["direction"], t["entry_underlying"],
                                                           t["stop_underlying"], settings.FNO_REENTRY_MARGIN_R)
        state = EntryState(pool=book.equity, open_premium=open_premium, open_positions=len(book.open),
                           trades_today=book.entries_today[today], active_kill_switches=halts,
                           held_symbols=held, is_trading_day=True, is_expiry_day=today in obs.expiries,
                           risk_multiplier=stance.multiplier, reentry_levels=levels)
        plan = plan_single_leg_entry(sig, snap, regime, now, state)
        self.decisions.append({"at": now.isoformat(), "bar_ts": sig.bar_ts, "direction": sig.direction.value,
                               "outcome": "accepted" if plan.accepted else plan.reject_reason,
                               "halts": list(state.active_kill_switches), "pool": round(state.pool, 2),
                               "risk_multiplier": stance.multiplier, "risk_reason": stance.reason})
        if not plan.accepted:
            self.funnel[plan.reject_reason] += 1
            return
        self.funnel["accepted"] += 1
        fill = plan.quote.ask
        leg = OpenLeg(
            initial_qty=plan.lots * plan.lot_size, id=book.next_id, tradingsymbol=plan.quote.contract.tradingsymbol, token=plan.quote.contract.token,
            direction=sig.direction.value, lots=plan.lots, lot_size=plan.lot_size, entry_time=now.isoformat(),
            entry_premium=fill, entry_underlying=snap.forward, stop_underlying=sig.stop_underlying,
            target_underlying=sig.target_underlying,
            premium_stop=round((1.0 - settings.FNO_STOP_PREMIUM_PCT) * fill, 2),
            atr_at_entry=sig.atr, delta_at_entry=plan.delta, bar_ts=sig.bar_ts, best_underlying=snap.forward)
        book.next_id += 1
        book.open[leg.id] = leg
        book.entered_bars.add(sig.bar_ts)
        book.entries_today[today] += 1

    # -- run -------------------------------------------------------------
    def run(self, start: str, end: str) -> dict:
        from config import settings
        days = [d for d in self.data.days if start <= d <= end]
        if not days:
            raise FnoReplayError("no archived sessions in the requested window")
        first = IST.localize(datetime.combine(date.fromisoformat(days[0]), time(0, 0)))
        closes = self.data.paper_closes()
        prior = [(at, pnl, kind) for at, pnl, kind in closes if at < first]
        exogenous = [(at, pnl, kind) for at, pnl, kind in closes if at >= first and kind == "DEFINED_RISK"]
        from fno_adaptive_risk import Close
        book = Book(equity=float(settings.FNO_PAPER_BANKROLL) + sum(pnl for _, pnl, _ in prior), closes=list(prior),
                    completed=[Close(at, pnl, kind == "SINGLE_LEG") for at, pnl, kind in prior])
        start_equity = book.equity
        exclusions: Counter = Counter()
        for day in days:
            observations, excluded = self.data.observations(day)
            exclusions.update(excluded)
            if not observations:
                self.notes["session_without_observations"] += 1
                continue
            session_day = date.fromisoformat(day)
            frame = self.data.futures_frame(observations[0].future.contract.token, session_day)
            phase = self.data.live_tick_phase(day)
            self.notes["grid_phase_live_aligned" if phase is not None else "grid_phase_default"] += 1
            grid = IST.localize(datetime.combine(session_day, SESSION_START)) + timedelta(seconds=phase or 0.0)
            for obs in observations:
                on_grid = obs.at >= grid
                if on_grid:
                    while grid <= obs.at:
                        grid += timedelta(seconds=GRID_SECONDS)
                if not (on_grid or (self.policy.manage_every_observation and book.open)):
                    continue
                now = obs.at
                self._apply_exogenous(book, exogenous, now)
                self._manage(book, obs, now)
                if on_grid:
                    self._entry(book, obs, frame, day, now)
            for leg in list(book.open.values()):
                self.notes["unresolved_at_session_end"] += 1
                book.trades.append({**asdict(leg), "status": "UNRESOLVED"})
            book.open.clear()
        self._apply_exogenous(book, exogenous, IST.localize(datetime.combine(
            date.fromisoformat(days[-1]), time(23, 59))))
        return {"policy": asdict(self.policy), "window": [days[0], days[-1]], "sessions": len(days),
                "start_equity": round(start_equity, 2), "trades": book.trades,
                "summary": summarize([t for t in book.trades if "net_pnl" in t]),
                "funnel": dict(sorted(self.funnel.items())), "notes": dict(sorted(self.notes.items())),
                "decisions": self.decisions,
                "archive_exclusions": dict(sorted(exclusions.items()))}


def summarize(trades: list[dict]) -> dict:
    net = [t["net_pnl"] for t in trades]
    running = peak = drawdown = 0.0
    for trade in sorted(trades, key=lambda t: t["exit_time"]):
        running += trade["net_pnl"]
        peak, drawdown = max(peak, running), max(drawdown, peak - running)
    best = max(net) if net else 0.0
    return {"closed": len(net), "net_pnl": round(sum(net), 4),
            "net_excluding_best_winner": round(sum(net) - max(best, 0.0), 4),
            "max_drawdown": round(drawdown, 4),
            "win_rate_pct": round(100 * sum(x > 0 for x in net) / len(net), 2) if net else None,
            "profit_factor": (round(sum(x for x in net if x > 0) / abs(sum(x for x in net if x < 0)), 4)
                              if any(x < 0 for x in net) else None),
            "exit_reasons": dict(sorted(Counter(t["exit_reason"] for t in trades).items()))}


def parity_report(replayed: list[dict], live: list[dict]) -> dict:
    """Match replayed and live trades by signal bar and contract."""
    def key(row):
        return (row["bar_ts"], row["tradingsymbol"])
    live_by, replay_by = {key(r): r for r in live}, {key(r): r for r in replayed if "net_pnl" in r}
    matched = []
    for k in sorted(set(live_by) & set(replay_by)):
        a, b = live_by[k], replay_by[k]
        matched.append({"bar_ts": k[0], "tradingsymbol": k[1],
                        "entry_premium": [a["entry_premium"], b["entry_premium"]],
                        "exit_reason": [a["exit_reason"], b["exit_reason"]],
                        "pnl": [round(float(a["pnl"]), 2), round(b["net_pnl"], 2)]})
    return {"live_trades": len(live), "replayed_trades": len(replay_by), "matched": matched,
            "live_only": sorted(set(live_by) - set(replay_by)),
            "replay_only": sorted(set(replay_by) - set(live_by))}


def run_replay(root: str | Path, *, start: str, end: str, policy: str = "BASELINE") -> dict:
    data = ReplayData(root)
    result = SingleLegReplay(data, POLICIES[policy]).run(start, end)
    result["parity_vs_live"] = parity_report(result["trades"], data.live_single_leg(start, end))
    result["dataset"] = {k: data.manifest[k] for k in ("schema", "source", "quote_days", "unsealed_days")}
    return result


if __name__ == "__main__":  # pragma: no cover - research CLI
    import argparse
    import sys
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("--data", required=True)
    cli.add_argument("--start", required=True)
    cli.add_argument("--end", required=True)
    cli.add_argument("--policy", default="BASELINE", choices=sorted(POLICIES))
    args = cli.parse_args()
    json.dump(run_replay(args.data, start=args.start, end=args.end, policy=args.policy), sys.stdout,
              indent=2, default=str)
