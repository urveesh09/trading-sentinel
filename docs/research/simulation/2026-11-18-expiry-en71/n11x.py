"""EN76: the pinned normal-F&O dispatcher, run in its own isolated process (PLAN7.md).

Source: `git archive 55b5e942 python-engine` (the Production checkout) in _local/pinned, with no .env beside it, so the
settings are the shipped defaults (recorded in the output). The Dev copies of these modules are identical at HEAD.
Dispatch, as fno_orchestrator.py's N11 branch (lines 1849-1864): first fno_engine_mom.evaluate_fno_mom (SENSEX passes
NIFTY's futures frame as rvol_bars), then fno_book.n11_signal(fno_book.with_participation(bars, rvol_bars), ...) with
yesterday's NIFTY daily ADX side (fno_book.daily_adx / adx_side; daily bars from Breeze index minutes). EFF's retest
state is the module's own, evaluated on every closed 5-minute bar from the open, in date order, in this process only.
The research adapter lets an expiry date into the signal evaluator only; nothing here touches the orchestrator, its
expiry skip, an executor or any runtime database. Regime: 'REGIME_1_NORMAL' (the VIX crisis label is not reconstructed;
only REGIME_3_CRISIS changes these functions).

    python -I n11x.py <days.json> <out.json>      days.json: [[und, day(, from_minute)], ...]
"""
from __future__ import annotations
import hashlib, json, sys
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
PINNED = HERE / "_local" / "pinned" / "python-engine"
REGIME = "REGIME_1_NORMAL"
SETTINGS = ("FNO_BOOK", "FNO_BOOK_ADX_MIN", "FNO_BOOK_MAX_STRETCH", "FNO_OR_MINUTES", "FNO_RVOL_LOOKBACK_DAYS", "FNO_MIN_RVOL", "FNO_ATR_LEN",
            "FNO_EMA_FAST", "FNO_EMA_SLOW", "FNO_OR_BUFFER_ATR", "FNO_STOP_ATR_MULT", "FNO_TARGET_R", "FNO_N11_LOW_LAST_MIN")
_ENG = {}


def engine():
    if not _ENG:
        for m in ("config", "fno_book", "fno_engine_mom", "fno_shadow"):
            assert m not in sys.modules, f"{m} already imported from elsewhere: run n11x in its own process"
        sys.path.insert(0, str(PINNED))
        import config, fno_book, fno_engine_mom, fno_shadow  # noqa: E401
        for mod in (config, fno_book, fno_engine_mom, fno_shadow):
            assert Path(mod.__file__).resolve().parent == PINNED.resolve(), mod.__file__
        assert not (PINNED / ".env").exists() and not (PINNED.parent / ".env").exists()
        _ENG.update(config=config, fno_book=fno_book, fno_engine_mom=fno_engine_mom, fno_shadow=fno_shadow)
    return _ENG


def tree_sha():
    h = hashlib.sha256()
    for p in sorted(PINNED.rglob("*.py")):
        h.update(p.relative_to(PINNED).as_posix().encode()); h.update(p.read_bytes())
    return h.hexdigest()


def day_signals(und, day, daily, from_min=0):
    """Every closed 5-minute bar of the day (from_min > 0: only bars starting at or after that minute; EFF's 15-minute
    retest cannot reach 13:00 from before 12:30, so the afternoon-only mode used for normal days changes no 13:00+ signal)."""
    import fut7
    eng = engine(); fb, mom = eng["fno_book"], eng["fno_engine_mom"]
    bars_all = fut7.frame5(und, day, 21); rv_all = fut7.frame5("NIFTY", day, 21) if und == "SENSEX" else None
    part = bars_all if rv_all is None else rv_all
    v, _ = fb.daily_adx(daily, date.fromisoformat(day)); side = fb.adx_side(v)
    fb._RETEST.clear()                                   # a retest never outlives its day (EffRetest.step checks the date)
    d0 = datetime.fromisoformat(day); out = []
    today = [ts for ts in bars_all.index if ts.date() == d0.date()]
    warm_days = len({ts.date() for ts in bars_all.index if ts.date() < d0.date()})
    for ts in today:
        if ts.hour * 60 + ts.minute < from_min:
            continue
        now = ts + timedelta(minutes=5, seconds=15)                    # the bar has closed; 15 s for receipt and evaluation
        pc = part[part.index + timedelta(minutes=5) <= now]
        rv = mom._rvol_time_adjusted(pc, ts) if ts in pc.index else None
        bars = bars_all[bars_all.index + timedelta(minutes=5) <= now]
        rvb = None if rv_all is None else rv_all[rv_all.index + timedelta(minutes=5) <= now]
        shipped = mom.evaluate_fno_mom(bars, REGIME, now) if rvb is None else mom.evaluate_fno_mom(bars, REGIME, now, rvol_bars=rvb)
        if not shipped.bar_ts:
            out.append(dict(m=ts.hour * 60 + ts.minute + 5, d=0, strategy="", why=f"engine:{shipped.reject_reason}", rvol=rv)); continue
        sig = fb.n11_signal(fb.with_participation(bars, rvb), REGIME, now, shipped=shipped, adx_side=side, underlying=und)
        d = 0 if sig.direction is None else (1 if sig.direction.value == "LONG" else -1)
        out.append(dict(m=ts.hour * 60 + ts.minute + 5, d=d, strategy=sig.strategy, why=sig.reject_reason, rvol=rv,
                        close=float(sig.close) if d else None, stop=float(sig.stop_underlying) if d else None))
    return dict(und=und, day=day, adx=v, adx_side=side, warm_sessions=warm_days, bars=len(today), signals=out)


def main(days_path, out_path):
    import fut7
    engine()
    daily = fut7.daily_frame("NIFTY")
    days = json.loads(Path(days_path).read_text())
    res = []
    for row in sorted(days, key=lambda x: (x[1], x[0])):
        und, day = row[0], row[1]; from_min = row[2] if len(row) > 2 else 0
        if not fut7.covered(und, day):
            res.append(dict(und=und, day=day, missing="no front-future minutes")); continue
        res.append(dict(day_signals(und, day, daily, from_min), from_min=from_min))
    s = engine()["config"].settings
    out = dict(pinned_commit="55b5e942", pinned_tree_sha256=tree_sha(), regime=REGIME, settings={k: getattr(s, k) for k in SETTINGS},
               days=res)
    Path(out_path).write_text(json.dumps(out, default=float) + "\n", encoding="utf-8")
    print("N11X", len(res), "days")


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    main(sys.argv[1], sys.argv[2])
