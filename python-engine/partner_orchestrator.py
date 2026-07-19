"""
[PARTNER-TIPS 2026-07-18] Partner tips bot orchestration (WS5).

Owns the partner-facing jobs (wired in scheduler_setup.register_partner_
scheduler_jobs) and the partner_messages dedup/throttle table:

  - partner_scan_tick      cron */2min at :40s, 09:45-15:05  -> ORB signal tips
  - partner_analytics_tick cron minute 2-57/5, 09:20-15:30   -> wide-chain
        snapshot -> OI store -> PCR/IV/OI-wall/regime/halt/momentum events
  - partner_morning_brief  09:50 -> per-underlying levels + options context
  - partner_eod_wrap       15:40 -> day recap + signal outcomes + OI purge
  - partner_rv_refresh     09:10 -> per-underlying 20d realized vol cache

Scheduling is deliberately OFF the quarter-hour grid: the momentum
screener and penny scans burst the shared Kite limiter at :00/:15/:30/:45
and partner calls must never queue ahead of the trading path at those
moments (plan: Performance isolation §1).

Every job's FIRST check is partner_enabled(): disabled means an
immediate return -- zero Kite calls, zero DB writes, zero log lines.

`kite`, `is_trading_day`, `_fno_regime_str` etc. are resolved through
`import main` on every call, the scheduler_setup convention the test
suite's patch-by-name discipline depends on.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiosqlite
import pytz
import structlog

import fno_analytics
import fno_oi_store
import options_math
from config import settings
from fno_chain import RISK_FREE_RATE, take_chain_snapshot, years_to_expiry
from fno_engine_mom import SESSION_OPEN_MIN
from fno_models import FnoDirection
from fno_signal_scan import scan_underlying
from fno_underlyings import analytics_underlyings, get_instruments_for, load_underlying_names
from macro_events import event_note_for
from partner_bot import partner_enabled, send_partner
from partner_content import (
    format_eod,
    format_event,
    format_morning_brief,
    format_signal_tip,
)

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

# In-memory per-day state (reset implicitly by date checks / restarts;
# everything that must survive a restart lives in partner_messages).
_rv_cache: Dict[str, float] = {}
_last_iv_reported: Dict[str, float] = {}
_last_walls_reported: Dict[str, tuple] = {}
# [PARTNER-ENRICH 2026-07-19] last-reported wall-OI delta per
# (underlying, strike, opt_type); re-report only on a further move of
# PARTNER_WALL_DELTA_PCT. Restart cost: one possibly-repeated event.
_last_wall_flow_reported: Dict[tuple, float] = {}
_last_regime_reported: Optional[str] = None
_halt_reported_on: Optional[str] = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS partner_messages (
  sent_at   TEXT NOT NULL,
  kind      TEXT NOT NULL,
  dedup_key TEXT NOT NULL,
  delivered INTEGER NOT NULL DEFAULT 0,
  detail    TEXT,
  PRIMARY KEY (kind, dedup_key)
);
"""


async def init_partner_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


# ---------------------------------------------------------------------------
# dedup / throttle
# ---------------------------------------------------------------------------

async def _seen(db_path: str, kind: str, key: str) -> bool:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT 1 FROM partner_messages WHERE kind=? AND dedup_key=?",
            (kind, key),
        )
        return await cur.fetchone() is not None


async def _record(
    db_path: str, kind: str, key: str, delivered: bool,
    detail: Optional[dict] = None, now: Optional[datetime] = None,
) -> None:
    ts = (now or datetime.now(IST)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO partner_messages "
            "(sent_at, kind, dedup_key, delivered, detail) VALUES (?,?,?,?,?)",
            (ts, kind, key, 1 if delivered else 0,
             json.dumps(detail) if detail else None),
        )
        await db.commit()


async def _throttled(
    db_path: str, kind: str, key: str, now: datetime,
) -> bool:
    """True when a (kind, key) message went out inside the gap window.
    Event kinds re-use the same dedup_key (the underlying), so the row's
    sent_at IS the last-send time."""
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT sent_at FROM partner_messages WHERE kind=? AND dedup_key=?",
            (kind, key),
        )
        row = await cur.fetchone()
    if row is None:
        return False
    try:
        last = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return False
    gap = timedelta(minutes=settings.PARTNER_EVENT_MIN_GAP_MIN)
    return (now.replace(tzinfo=None) - last) < gap


async def _send_event(
    db_path: str, kind: str, name: str, detail: str, now: datetime,
    throttle_key: Optional[str] = None,
) -> None:
    """Throttle key defaults to the underlying (one event of a kind per
    underlying per gap). Pass throttle_key when a single kind can fire
    more than once per tick per underlying (wall_flow: support AND
    resistance) so the two don't collide on one shared row."""
    key = throttle_key or name or kind
    if await _throttled(db_path, kind, key, now):
        return
    ok = await send_partner(format_event(kind, name, detail), kind=kind)
    await _record(db_path, kind, key, ok, now=now)


# ---------------------------------------------------------------------------
# shared gates
# ---------------------------------------------------------------------------

async def _gates_open(now: datetime, lo_min: int, hi_min: int) -> bool:
    """enabled -> session window -> trading day -> fresh-ish token.
    Ordered cheapest-first; the enabled check is the zero-cost no-op."""
    if not partner_enabled():
        return False
    nm = now.hour * 60 + now.minute
    if not (lo_min <= nm <= hi_min):
        return False
    import main as _main
    if not await _main.is_trading_day(now.date(), settings.DB_PATH):
        return False
    if not _main.kite.access_token:
        return False
    return True


def _expiry_note_for(name: str, now: datetime, iv: Optional[float]) -> str:
    book = get_instruments_for(name)
    return fno_analytics.expiry_note(
        book.nearest_option_expiry(now.date()), now.date(), iv
    )


def _dte_for(name: str, now: datetime) -> Optional[int]:
    expiry = get_instruments_for(name).nearest_option_expiry(now.date())
    return (expiry - now.date()).days if expiry is not None else None


# ---------------------------------------------------------------------------
# rolling track record ([PARTNER-ENRICH 2026-07-19] T1c)
# ---------------------------------------------------------------------------

async def _track_record(
    db_path: str, name: str, direction: str, now: datetime,
) -> str:
    """One-line rolling record for (underlying, direction) from signal
    rows whose EOD pass stamped an outcome. '' below the minimum sample
    — a 3-signal 'record' is noise dressed as evidence, and today's
    not-yet-resolved signals are naturally excluded (no outcome yet)."""
    since = (
        now - timedelta(days=settings.PARTNER_TRACK_LOOKBACK_DAYS)
    ).strftime("%Y-%m-%d 00:00:00")
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT detail FROM partner_messages "
            "WHERE kind='signal' AND dedup_key LIKE ? AND sent_at>=?",
            (f"{name}:%", since),
        )
        rows = await cur.fetchall()
    n = hits = 0
    r_sum = 0.0
    for (detail_json,) in rows:
        if not detail_json:
            continue
        try:
            d = json.loads(detail_json)
        except json.JSONDecodeError:
            continue
        if d.get("direction") != direction or d.get("outcome_kind") is None:
            continue
        r = d.get("outcome_r")
        if not isinstance(r, (int, float)):
            continue
        n += 1
        r_sum += float(r)
        if d.get("outcome_kind") == "target":
            hits += 1
    if n < settings.PARTNER_TRACK_MIN_N:
        return ""
    return (
        f"Record ({name} {direction}, {settings.PARTNER_TRACK_LOOKBACK_DAYS}d): "
        f"{hits}/{n} target-first, avg {r_sum / n:+.1f}R on the underlying"
    )


# ---------------------------------------------------------------------------
# job: signal scan tick (ORB tips)
# ---------------------------------------------------------------------------

async def partner_scan_tick(now: Optional[datetime] = None) -> None:
    now = now or datetime.now(IST)
    if not await _gates_open(now, 9 * 60 + 45, 15 * 60 + 5):
        return
    import main as _main
    logger.info("partner_scan_tick_invoked now_ist=%s", now.strftime("%H:%M:%S"))
    regime = _main._fno_regime_str()
    for spec in analytics_underlyings():
        if not spec.signal_enabled:
            continue
        try:
            scan = await scan_underlying(_main.kite, spec, regime, now)
            sig = scan.sig
            if sig is None or sig.direction is None:
                continue
            key = f"{spec.name}:{sig.bar_ts}"
            if await _seen(settings.DB_PATH, "signal", key):
                continue

            option = None
            if scan.pick is not None and scan.snap is not None:
                q, iv, d = scan.pick
                is_call = sig.direction == FnoDirection.LONG
                T = years_to_expiry(scan.snap.expiry, now)
                theta_day = options_math.theta(
                    scan.snap.forward, q.contract.strike, T, iv,
                    RISK_FREE_RATE, is_call,
                )
                option = {
                    "tradingsymbol": q.contract.tradingsymbol,
                    # A buyer pays the ask; quoting mid would flatter the fill.
                    "premium": q.ask if q.ask > 0 else q.mid,
                    "iv": iv,
                    "delta": d,
                    "theta_day": theta_day,
                    "spread_pct": q.spread_pct if q.spread_pct != float("inf") else None,
                    "oi": q.oi,
                }
                # [PARTNER-ENRICH 2026-07-19] T1a/T1d: premium-terms
                # stop/target scenarios + lot-level sizing. Both degrade
                # to absent lines rather than made-up numbers.
                scen = fno_analytics.premium_scenarios(
                    scan.snap.forward, q.contract.strike, T, iv, is_call,
                    option["premium"], sig.stop_underlying, sig.target_underlying,
                )
                if scen is not None:
                    option.update(
                        prem_at_target=scen["at_target"],
                        prem_at_stop=scen["at_stop"],
                        rr_premium=scen["rr"],
                    )
                    lot = q.contract.lot_size
                    risk_per_lot = (option["premium"] - scen["at_stop"]) * lot
                    if lot > 0 and risk_per_lot > 0:
                        budget = 100_000 * settings.PARTNER_SIZING_RISK_PCT
                        option.update(
                            lot_size=lot,
                            risk_per_lot=risk_per_lot,
                            lots_per_lakh=int(budget // risk_per_lot),
                            sizing_risk_pct=settings.PARTNER_SIZING_RISK_PCT,
                        )

            broken = sig.or_high + settings.FNO_OR_BUFFER_ATR * sig.atr \
                if sig.direction == FnoDirection.LONG \
                else sig.or_low - settings.FNO_OR_BUFFER_ATR * sig.atr
            or_atr_ratio = (
                (sig.or_high - sig.or_low) / sig.atr if sig.atr > 0 else None
            )
            track_line = await _track_record(
                settings.DB_PATH, spec.name, sig.direction.value, now,
            )
            msg = format_signal_tip(
                name=spec.name,
                direction=sig.direction.value,
                bar_time=sig.bar_ts[11:16] if len(sig.bar_ts) >= 16 else sig.bar_ts,
                close=sig.close,
                broken_level=broken,
                stop=sig.stop_underlying,
                target=sig.target_underlying,
                regime=regime,
                rvol=sig.rvol,
                expiry_note=_expiry_note_for(
                    spec.name, now, option.get("iv") if option else None
                ),
                option=option,
                thin_reasons=scan.thin_reasons if scan.thin_chain else None,
                or_atr_ratio=or_atr_ratio,
                track_line=track_line,
            )
            ok = await send_partner(msg, kind="signal")
            detail = {
                "direction": sig.direction.value,
                "bar_ts": sig.bar_ts,
                "close": sig.close,
                "stop": sig.stop_underlying,
                "target": sig.target_underlying,
            }
            if option and scan.pick is not None and scan.snap is not None:
                # Enough to find this strike's LTP series in fno_chain_oi
                # at EOD (T2b) without re-resolving instruments.
                detail.update(
                    tradingsymbol=option["tradingsymbol"],
                    strike=scan.pick[0].contract.strike,
                    opt_type="CE" if sig.direction == FnoDirection.LONG else "PE",
                    expiry=scan.snap.expiry.isoformat(),
                    premium_paid=option["premium"],
                )
            await _record(settings.DB_PATH, "signal", key, ok, detail=detail, now=now)
        except Exception as exc:
            logger.error(
                "partner_scan_tick_failed underlying=%s err=%s",
                spec.name, str(exc), exc_info=True,
            )


# ---------------------------------------------------------------------------
# job: analytics tick (wide chain -> OI store -> events)
# ---------------------------------------------------------------------------

async def partner_analytics_tick(now: Optional[datetime] = None) -> None:
    global _last_regime_reported, _halt_reported_on
    now = now or datetime.now(IST)
    if not await _gates_open(now, 9 * 60 + 20, 15 * 60 + 30):
        return
    import main as _main
    logger.info("partner_analytics_tick_invoked now_ist=%s", now.strftime("%H:%M:%S"))
    day_iso = now.date().isoformat()
    oi_events_open = (now.hour * 60 + now.minute) >= 10 * 60  # OI delayed early

    for spec in analytics_underlyings():
        try:
            book = get_instruments_for(spec.name)
            if not book.ready(now.date()):
                continue
            snap = await take_chain_snapshot(
                _main.kite, book, now,
                strike_window=settings.FNO_ANALYTICS_STRIKE_WINDOW,
            )
            if snap is None:
                continue
            pcr = fno_analytics.compute_pcr(snap)
            max_pain = fno_analytics.compute_max_pain(snap)
            iv = fno_analytics.atm_iv(snap, now)
            await fno_oi_store.persist_snapshot(
                settings.DB_PATH, spec.name, snap, pcr, max_pain, iv,
            )

            # --- IV spike/crush vs last reported ------------------------
            if iv is not None:
                last_iv = _last_iv_reported.get(spec.name)
                if last_iv is None:
                    _last_iv_reported[spec.name] = iv
                elif last_iv > 0 and abs(iv - last_iv) / last_iv >= settings.PARTNER_IV_MOVE_ALERT_PCT:
                    word = "spiked" if iv > last_iv else "dropped"
                    await _send_event(
                        settings.DB_PATH, "iv_move", spec.name,
                        f"ATM IV {word} {last_iv * 100:.1f}% -> {iv * 100:.1f}% — "
                        + ("long premium just got pricier"
                           if iv > last_iv else
                           "premium crush; longs bleed even when right"),
                        now,
                    )
                    _last_iv_reported[spec.name] = iv

            if not oi_events_open:
                continue

            # --- PCR shift vs open (+ futures buildup color) -------------
            open_row = await fno_oi_store.first_fut_row_today(
                settings.DB_PATH, spec.name, day_iso,
            )
            if (
                open_row is not None and pcr is not None
                and open_row.get("pcr") is not None
                and abs(pcr - open_row["pcr"]) >= settings.PARTNER_PCR_ALERT_DELTA
            ):
                buildup = ""
                if snap.fut_quote and open_row.get("fut_ltp") and open_row.get("fut_oi"):
                    label = fno_analytics.classify_buildup(
                        snap.forward - open_row["fut_ltp"],
                        (snap.fut_quote.oi or 0) - open_row["fut_oi"],
                    )
                    if label != "NEUTRAL":
                        buildup = f" | futures: {label.replace('_', ' ').lower()}"
                bias = (
                    "put writing building — dip-support bias"
                    if pcr > open_row["pcr"]
                    else "call writing building — upside likely capped"
                )
                await _send_event(
                    settings.DB_PATH, "pcr_shift", spec.name,
                    f"PCR {open_row['pcr']:.2f} -> {pcr:.2f} since open — {bias}{buildup}",
                    now,
                )

            # --- OI wall migration --------------------------------------
            support, resistance = fno_analytics.oi_walls(snap)
            prev_walls = _last_walls_reported.get(spec.name)
            if support is not None and resistance is not None:
                if prev_walls is None:
                    _last_walls_reported[spec.name] = (support, resistance)
                elif (support, resistance) != prev_walls:
                    await _send_event(
                        settings.DB_PATH, "oi_walls", spec.name,
                        f"OI walls moved: support {prev_walls[0]:,.0f} -> {support:,.0f}"
                        f" | resistance {prev_walls[1]:,.0f} -> {resistance:,.0f}",
                        now,
                    )
                    _last_walls_reported[spec.name] = (support, resistance)

            # --- wall build/unwind vs open baseline ---------------------
            # [PARTNER-ENRICH 2026-07-19] T2a: a wall that ADDS OI while
            # price approaches is being defended; one that unwinds is
            # likely to break. Far more tradeable than "walls moved".
            baseline = await fno_oi_store.open_baseline(
                settings.DB_PATH, spec.name, day_iso,
            )
            if baseline:
                deltas = fno_analytics.strike_oi_deltas(snap, baseline)
                wall_reads = (
                    (support, "PE", "Support",
                     "put writers adding — dip-support being defended",
                     "put writers bailing — support weakening"),
                    (resistance, "CE", "Resistance",
                     "call writers pressing — upside capped for now",
                     "call writers covering — breakout risk above"),
                )
                for strike, ot, side, build_txt, unwind_txt in wall_reads:
                    if strike is None:
                        continue
                    base_oi = baseline.get((strike, ot))
                    delta = deltas.get((strike, ot))
                    if not base_oi or delta is None:
                        continue
                    pct = delta / base_oi
                    flow_key = (spec.name, strike, ot)
                    last_pct = _last_wall_flow_reported.get(flow_key, 0.0)
                    if (
                        abs(pct) >= settings.PARTNER_WALL_DELTA_PCT
                        and abs(pct - last_pct) >= settings.PARTNER_WALL_DELTA_PCT
                    ):
                        await _send_event(
                            settings.DB_PATH, "wall_flow", spec.name,
                            f"{side} {strike:,.0f} {ot} OI {pct:+.0%} vs open — "
                            + (build_txt if pct > 0 else unwind_txt),
                            now,
                            # support (PE) and resistance (CE) throttle
                            # independently -- both can move in one tick.
                            throttle_key=f"{spec.name}:{ot}",
                        )
                        _last_wall_flow_reported[flow_key] = pct

            # --- expiry-day pin note ------------------------------------
            # [PARTNER-ENRICH 2026-07-19] T3a: once per expiry afternoon.
            if (
                book.is_expiry_day(now.date())
                and (now.hour * 60 + now.minute) >= 13 * 60 + 30
                and max_pain is not None and snap.forward > 0
            ):
                pin_key = f"{spec.name}:{day_iso}"
                if not await _seen(settings.DB_PATH, "pin", pin_key):
                    dist = snap.forward - max_pain
                    ok = await send_partner(
                        format_event(
                            "pin", spec.name,
                            f"expiry pin watch: fut {snap.forward:,.0f} vs "
                            f"max pain {max_pain:,.0f} ({dist:+,.0f} pts) — "
                            "price often gravitates toward max pain into the "
                            "close; chasing moves away from it is fighting "
                            "the writers",
                        ),
                        kind="pin",
                    )
                    await _record(settings.DB_PATH, "pin", pin_key, ok, now=now)
        except Exception as exc:
            logger.error(
                "partner_analytics_tick_failed underlying=%s err=%s",
                spec.name, str(exc), exc_info=True,
            )

    # --- regime transition (index-level, one per tick) -------------------
    try:
        regime = _main._fno_regime_str()
        if _last_regime_reported is None:
            _last_regime_reported = regime
        elif regime != _last_regime_reported:
            await _send_event(
                settings.DB_PATH, "regime_change", "",
                f"Market regime changed: {_last_regime_reported} -> {regime}"
                + (" — our system stops taking new entries in CRISIS"
                   if regime == "REGIME_3_CRISIS" else ""),
                now,
            )
            _last_regime_reported = regime
    except Exception as exc:
        logger.warning("partner_regime_event_failed err=%s", str(exc))

    # --- system halt notice (informational) ------------------------------
    try:
        async with _main.state_lock:
            halted, reasons = await _main.check_circuit_breakers(settings.DB_PATH)
        if halted and _halt_reported_on != day_iso:
            _halt_reported_on = day_iso
            await _send_event(
                settings.DB_PATH, "halt", "",
                "Our system halted its own trading today ("
                + "; ".join(reasons[:3])
                + ") — treat signals with extra caution",
                now,
            )
    except Exception as exc:
        logger.warning("partner_halt_event_failed err=%s", str(exc))

    # --- momentum stock-option cues --------------------------------------
    try:
        fno_names = load_underlying_names()
        if fno_names:
            for s in list(getattr(_main, "momentum_signals_today", [])):
                ticker = getattr(s, "ticker", None)
                if not ticker or ticker.upper() not in fno_names:
                    continue
                key = f"{ticker.upper()}:{day_iso}"
                if await _seen(settings.DB_PATH, "mom_cue", key):
                    continue
                vol_ratio = getattr(s, "volume_ratio", 0.0) or 0.0
                close = getattr(s, "close", 0.0) or 0.0
                # [PARTNER-ENRICH 2026-07-19] T3b: the screener's own
                # levels make the cue actionable instead of a headline.
                stop_loss = getattr(s, "stop_loss", 0.0) or 0.0
                target_1 = getattr(s, "target_1", 0.0) or 0.0
                levels = ""
                if stop_loss > 0 and target_1 > 0:
                    levels = (
                        f" (screener stop {stop_loss:,.1f} / "
                        f"target {target_1:,.1f} on the stock)"
                    )
                ok = await send_partner(
                    format_event(
                        "mom_cue", ticker.upper(),
                        f"our momentum screener fired at {close:,.1f} on "
                        f"{vol_ratio:.1f}x volume{levels} — F&O-listed, "
                        "stock options are a way to play it",
                    ),
                    kind="mom_cue",
                )
                await _record(settings.DB_PATH, "mom_cue", key, ok, now=now)
    except Exception as exc:
        logger.warning("partner_mom_cue_failed err=%s", str(exc))


# ---------------------------------------------------------------------------
# job: morning brief
# ---------------------------------------------------------------------------

async def partner_morning_brief(now: Optional[datetime] = None) -> None:
    now = now or datetime.now(IST)
    if not await _gates_open(now, 0, 24 * 60):
        return
    import main as _main
    day_iso = now.date().isoformat()
    if await _seen(settings.DB_PATH, "brief", day_iso):
        return
    logger.info("partner_morning_brief_invoked now_ist=%s", now.strftime("%H:%M:%S"))
    regime = _main._fno_regime_str()
    score = None
    try:
        state = getattr(_main, "_last_regime_state", None)
        if state is not None:
            score = float(getattr(state, "regime_score", None))
    except (TypeError, ValueError):
        score = None

    rows: List[Dict] = []
    for spec in analytics_underlyings():
        row: Dict = {"name": spec.name}
        try:
            book = get_instruments_for(spec.name)
            if not book.ready(now.date()):
                row["error"] = "instruments not ready"
                rows.append(row)
                continue
            scan = await scan_underlying(_main.kite, spec, regime, now)
            sig = scan.sig
            if sig is not None and sig.or_high > 0:
                row.update(
                    or_high=sig.or_high, or_low=sig.or_low, atr=sig.atr,
                    long_level=sig.or_high + settings.FNO_OR_BUFFER_ATR * sig.atr,
                    short_level=sig.or_low - settings.FNO_OR_BUFFER_ATR * sig.atr,
                    fut=sig.close,
                    or_atr_ratio=(
                        (sig.or_high - sig.or_low) / sig.atr
                        if sig.atr > 0 else None
                    ),
                )
            snap = await take_chain_snapshot(
                _main.kite, book, now,
                strike_window=settings.FNO_ANALYTICS_STRIKE_WINDOW,
            )
            if snap is not None:
                pcr = fno_analytics.compute_pcr(snap)
                max_pain = fno_analytics.compute_max_pain(snap)
                iv = fno_analytics.atm_iv(snap, now)
                support, resistance = fno_analytics.oi_walls(snap)
                skew = fno_analytics.atm_iv_skew(snap, now)
                await fno_oi_store.persist_snapshot(
                    settings.DB_PATH, spec.name, snap, pcr, max_pain, iv,
                )
                rv = _rv_cache.get(spec.name)
                row.update(
                    fut=row.get("fut") or snap.forward,
                    pcr=pcr, max_pain=max_pain, iv=iv, rv=rv,
                    iv_read=fno_analytics.iv_rv_read(iv, rv),
                    support=support, resistance=resistance,
                    expiry_note=_expiry_note_for(spec.name, now, iv),
                    dte=_dte_for(spec.name, now),
                )
                if skew is not None:
                    row.update(skew_ce=skew[0], skew_pe=skew[1])
            elif "fut" not in row:
                row["error"] = scan.error or "no data"
        except Exception as exc:
            logger.error(
                "partner_brief_underlying_failed name=%s err=%s",
                spec.name, str(exc), exc_info=True,
            )
            row["error"] = "internal error"
        rows.append(row)

    msg = format_morning_brief(
        f"{day_iso} {now.strftime('%H:%M')} IST", regime, score, rows,
        events_note=event_note_for(now.date()),
    )
    ok = await send_partner(msg, kind="brief")
    await _record(settings.DB_PATH, "brief", day_iso, ok, now=now)


# ---------------------------------------------------------------------------
# job: EOD wrap (+ retention purges)
# ---------------------------------------------------------------------------

def _signal_outcome(bars, detail: dict):
    """Walk today's 5-min bars after the signal bar: which of target/stop
    printed first? Purely informational -- our own exits (trail/time/flat)
    are not modeled here; the partner saw stop+target in the tip.

    Returns (text, kind, r): kind in target|stop|neither|None (None =
    outcome unavailable), r = underlying-R vs the tip's risk (target hit
    counts the actual target distance, stop -1.0, neither = close-to-
    close move in R). kind/r feed the persisted track record (T1c)."""
    try:
        import pandas as pd  # noqa: F401  (bars is a DataFrame)
        bar_ts = datetime.strptime(detail["bar_ts"], "%Y-%m-%d %H:%M:%S")
        after = bars[bars.index > bar_ts]
        long_view = detail["direction"] == "LONG"
        entry = float(detail["close"])
        stop, target = float(detail["stop"]), float(detail["target"])
        risk = abs(entry - stop)
        r_target = (abs(target - entry) / risk) if risk > 0 else 1.5
        for _, b in after.iterrows():
            hi, lo = float(b["high"]), float(b["low"])
            if long_view:
                if lo <= stop:
                    return f"stop {stop:,.0f} hit first", "stop", -1.0
                if hi >= target:
                    return f"target {target:,.0f} hit", "target", r_target
            else:
                if hi >= stop:
                    return f"stop {stop:,.0f} hit first", "stop", -1.0
                if lo <= target:
                    return f"target {target:,.0f} hit", "target", r_target
        close = float(bars["close"].iloc[-1]) if len(bars) else 0.0
        pts = (close - entry) * (1 if long_view else -1)
        r = (pts / risk) if risk > 0 else 0.0
        return (
            f"neither printed; closed {close:,.0f} ({pts:+,.0f} pts)",
            "neither", r,
        )
    except Exception:
        return "outcome unavailable", None, None


async def _stamp_outcome(
    db_path: str, key: str, detail: dict, kind: str, r,
) -> None:
    """Write outcome fields back into the signal row's detail JSON so the
    rolling track record (T1c) can read resolved signals later. UPDATE
    keeps sent_at intact (it doubles as the retention timestamp)."""
    detail = dict(detail)
    detail["outcome_kind"] = kind
    detail["outcome_r"] = round(float(r), 3) if r is not None else None
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE partner_messages SET detail=? "
            "WHERE kind='signal' AND dedup_key=?",
            (json.dumps(detail), key),
        )
        await db.commit()


async def _option_outcome_line(detail: dict, day_iso: str) -> str:
    """[PARTNER-ENRICH 2026-07-19] T2b: what the SUGGESTED OPTION's
    premium did after the tip, from the 5-min chain snapshots already in
    fno_chain_oi. '' when the strike wasn't snapshotted (window moved)
    or the tip carried no option."""
    symbol = detail.get("tradingsymbol")
    paid = detail.get("premium_paid")
    strike = detail.get("strike")
    opt_type = detail.get("opt_type")
    expiry = detail.get("expiry")
    if not (symbol and strike and opt_type and expiry) or not paid or paid <= 0:
        return ""
    series = await fno_oi_store.strike_ltp_series(
        settings.DB_PATH, detail.get("underlying", ""), day_iso,
        expiry, float(strike), opt_type,
        from_ts=detail.get("bar_ts"),
    )
    if not series:
        return ""
    ltps = [ltp for _, ltp in series]
    peak, last = max(ltps), ltps[-1]
    return (
        f"option {symbol}: paid ~{paid:,.1f}, "
        f"peak {peak:,.1f} ({(peak - paid) / paid:+.0%}), "
        f"last {last:,.1f} ({(last - paid) / paid:+.0%})"
    )


async def _track_record_overall(db_path: str, now: datetime) -> str:
    """All-underlyings, all-directions rolling record for the EOD wrap."""
    since = (
        now - timedelta(days=settings.PARTNER_TRACK_LOOKBACK_DAYS)
    ).strftime("%Y-%m-%d 00:00:00")
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT detail FROM partner_messages "
            "WHERE kind='signal' AND sent_at>=?",
            (since,),
        )
        rows = await cur.fetchall()
    n = hits = 0
    r_sum = 0.0
    for (detail_json,) in rows:
        if not detail_json:
            continue
        try:
            d = json.loads(detail_json)
        except json.JSONDecodeError:
            continue
        if d.get("outcome_kind") is None:
            continue
        r = d.get("outcome_r")
        if not isinstance(r, (int, float)):
            continue
        n += 1
        r_sum += float(r)
        if d.get("outcome_kind") == "target":
            hits += 1
    if n < settings.PARTNER_TRACK_MIN_N:
        return ""
    return (
        f"📊 Rolling {settings.PARTNER_TRACK_LOOKBACK_DAYS}d ORB record: "
        f"{hits}/{n} target-first, avg {r_sum / n:+.1f}R on the underlying"
    )


async def partner_eod_wrap(now: Optional[datetime] = None) -> None:
    now = now or datetime.now(IST)
    if not await _gates_open(now, 0, 24 * 60):
        return
    import main as _main
    day_iso = now.date().isoformat()
    if await _seen(settings.DB_PATH, "eod", day_iso):
        return
    logger.info("partner_eod_wrap_invoked now_ist=%s", now.strftime("%H:%M:%S"))

    rows: List[Dict] = []
    for spec in analytics_underlyings():
        row: Dict = {"name": spec.name}
        try:
            book = get_instruments_for(spec.name)
            fut = book.front_future(now.date()) if book.ready(now.date()) else None
            if fut is None:
                row["error"] = "instruments not ready"
                rows.append(row)
                continue
            bars = await _main.kite.get_intraday_by_token(
                fut.token, f"{day_iso} 09:15:00",
                now.strftime("%Y-%m-%d %H:%M:%S"), interval="5minute",
            )
            if bars is None or bars.empty:
                row["error"] = "no bars"
                rows.append(row)
                continue
            or_end = SESSION_OPEN_MIN + settings.FNO_OR_MINUTES
            or_bars = bars[[
                SESSION_OPEN_MIN <= (t.hour * 60 + t.minute) < or_end
                for t in bars.index
            ]]
            row.update(
                day_high=float(bars["high"].max()),
                day_low=float(bars["low"].min()),
                close=float(bars["close"].iloc[-1]),
                or_high=float(or_bars["high"].max()) if len(or_bars) else None,
                or_low=float(or_bars["low"].min()) if len(or_bars) else None,
            )

            sig_rows: List[Dict] = []
            async with aiosqlite.connect(settings.DB_PATH) as db:
                cur = await db.execute(
                    "SELECT dedup_key, detail FROM partner_messages "
                    "WHERE kind='signal' AND dedup_key LIKE ? ORDER BY dedup_key",
                    (f"{spec.name}:{day_iso}%",),
                )
                found = await cur.fetchall()
            for _key, detail_json in found:
                if not detail_json:
                    continue
                try:
                    detail = json.loads(detail_json)
                except json.JSONDecodeError:
                    continue
                outcome_txt, outcome_kind, outcome_r = _signal_outcome(bars, detail)
                if outcome_kind is not None:
                    await _stamp_outcome(
                        settings.DB_PATH, _key, detail, outcome_kind, outcome_r,
                    )
                detail["underlying"] = spec.name
                sig_rows.append({
                    "time": detail.get("bar_ts", "")[11:16],
                    "direction": detail.get("direction", "?"),
                    "outcome": outcome_txt,
                    "option_line": await _option_outcome_line(detail, day_iso),
                })
            row["signals"] = sig_rows

            last = await fno_oi_store.latest_fut_row(settings.DB_PATH, spec.name)
            if last is not None and last["snap_ts"].startswith(day_iso):
                row.update(pcr=last["pcr"], max_pain=last["max_pain"])
            if book.is_expiry_day(now.date() + timedelta(days=1)):
                row["tomorrow_note"] = (
                    f"{spec.name} expiry TOMORROW — theta burns fast, "
                    "avoid holding long premium overnight"
                )
        except Exception as exc:
            logger.error(
                "partner_eod_underlying_failed name=%s err=%s",
                spec.name, str(exc), exc_info=True,
            )
            row["error"] = "internal error"
        rows.append(row)

    msg = format_eod(
        day_iso, rows,
        record_line=await _track_record_overall(settings.DB_PATH, now),
    )
    ok = await send_partner(msg, kind="eod")
    await _record(settings.DB_PATH, "eod", day_iso, ok, now=now)

    # Retention: OI snapshots + old dedup rows. Disk at 86% -- this is
    # part of the job, not housekeeping that can silently stop running.
    # [PARTNER-ENRICH 2026-07-19] signal rows live longer than the rest:
    # the rolling track record (T1c) needs weeks, OI forensics needs days,
    # and a few signal rows/day is negligible disk.
    try:
        await fno_oi_store.purge_older_than(
            settings.DB_PATH, settings.FNO_OI_RETENTION_DAYS,
        )
        cutoff = (
            now - timedelta(days=settings.FNO_OI_RETENTION_DAYS)
        ).strftime("%Y-%m-%d 00:00:00")
        signal_cutoff = (
            now - timedelta(days=settings.PARTNER_SIGNAL_RETENTION_DAYS)
        ).strftime("%Y-%m-%d 00:00:00")
        async with aiosqlite.connect(settings.DB_PATH) as db:
            await db.execute(
                "DELETE FROM partner_messages WHERE sent_at<? AND kind!='signal'",
                (cutoff,),
            )
            await db.execute(
                "DELETE FROM partner_messages WHERE sent_at<? AND kind='signal'",
                (signal_cutoff,),
            )
            await db.commit()
    except Exception as exc:
        logger.warning("partner_purge_failed err=%s", str(exc))


# ---------------------------------------------------------------------------
# job: daily realized-vol refresh
# ---------------------------------------------------------------------------

RV_FETCH_CALENDAR_DAYS = 45   # >= 21 trading days of daily closes


async def partner_rv_refresh(now: Optional[datetime] = None) -> None:
    now = now or datetime.now(IST)
    if not await _gates_open(now, 0, 24 * 60):
        return
    import main as _main
    logger.info("partner_rv_refresh_invoked now_ist=%s", now.strftime("%H:%M:%S"))
    for spec in analytics_underlyings():
        try:
            book = get_instruments_for(spec.name)
            fut = book.front_future(now.date())
            if fut is None:
                continue
            frm = (now - timedelta(days=RV_FETCH_CALENDAR_DAYS)).strftime("%Y-%m-%d")
            # NOTE: futures dailies contaminate ~1 of 20 returns near the
            # contract roll; acceptable for a rich/cheap read (plan WS3.3;
            # index-token closes are the post-verification upgrade).
            bars = await _main.kite.get_intraday_by_token(
                fut.token, frm, now.strftime("%Y-%m-%d"), interval="day",
            )
            if bars is None or bars.empty or "close" not in bars:
                continue
            rv = fno_analytics.realized_vol_20d(bars["close"])
            if rv is not None:
                _rv_cache[spec.name] = rv
                logger.info(
                    "partner_rv_refreshed underlying=%s rv=%.3f", spec.name, rv,
                )
        except Exception as exc:
            logger.warning(
                "partner_rv_refresh_failed underlying=%s err=%s",
                spec.name, str(exc),
            )
