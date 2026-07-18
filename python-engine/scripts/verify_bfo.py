"""
[PARTNER-TIPS 2026-07-18] One-off BFO/SENSEX live verification (plan WS6).

Run BY HAND inside the python-engine container with a fresh Kite token:

    docker compose exec python-engine python scripts/verify_bfo.py

Gates rollout phase P3: SENSEX stays analytics-only (and
SPECS["SENSEX"].signal_enabled stays False) until every check below
passes. Checks:

  1. /instruments/BFO dump has SENSEX CE/PE/FUT rows with sane lot_size
     and a strike ladder; expiries readable (trust ONLY the dump for
     expiry weekdays -- they have changed several times).
  2. /quote accepts raw BFO instrument TOKENS (the token-int i= form is
     undocumented; it works for NFO in production, unverified for BFO).
  3. Mixed NFO+BFO tokens in one /quote batch (nice-to-have; fallback is
     per-underlying batches, which is the shipped default anyway).
  4. SENSEX front-future 5-min bars carry NON-GARBAGE volume (BSE index
     futures are thin; junk volume => RVOL never passes => ORB signals
     structurally absent => keep signal_enabled=False).
  5. interval="day" historicals for the RV sources (futures always;
     index tokens 256265/260105/265 as a bonus -- INDICES dump 403s on
     this plan per VERIFY-6, but historical-by-token may still work).
  6. BFO option quotes populate the oi field.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta

sys.path.insert(0, "/app")

import pytz  # noqa: E402

IST = pytz.timezone("Asia/Kolkata")

INDEX_TOKENS = {"NIFTY 50": 256265, "NIFTY BANK": 260105, "SENSEX": 265}


def _p(ok: bool, label: str, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    return ok


async def main() -> int:
    from main import kite  # engine singletons; needs the armed token

    if not kite.access_token:
        print("No access token -- log in first (POST /token). Aborting.")
        return 2

    now = datetime.now(IST)
    today = now.date()
    results = []

    # ---- 1. BFO dump --------------------------------------------------
    print("1. BFO instruments dump")
    from fno_instruments import FnoInstruments
    book = FnoInstruments(
        underlying="SENSEX", segment="BFO",
        json_path="/tmp/verify_bfo_sensex.json",
    )
    ok = await book.refresh(kite)
    results.append(_p(ok, "dump fetch + SENSEX rows parsed"))
    if ok:
        results.append(_p(book.lot_size > 0, f"lot_size={book.lot_size} (expect ~20)"))
        results.append(_p(
            book.strike_step > 0,
            f"strike_step={book.strike_step:.0f} (expect 100)",
        ))
        ne = book.nearest_option_expiry(today)
        results.append(_p(
            ne is not None,
            f"nearest option expiry={ne} (weekday {ne.strftime('%A') if ne else '?'})",
        ))
        fut = book.front_future(today)
        results.append(_p(fut is not None, f"front future={getattr(fut, 'tradingsymbol', None)}"))
    else:
        print("  -- cannot continue BFO checks without the dump")
        return 1

    # ---- 2. raw-token /quote for BFO ---------------------------------
    print("2. /quote with raw BFO tokens")
    fut = book.front_future(today)
    q = await kite.get_quote([fut.token])
    fut_q = q.get(fut.token) or {}
    results.append(_p(
        bool(fut_q.get("last_price")),
        f"SENSEX fut quote ltp={fut_q.get('last_price')}",
    ))

    # ---- 3. mixed NFO+BFO batch (nice-to-have) ------------------------
    print("3. mixed NFO+BFO /quote batch")
    try:
        from fno_instruments import get_fno_instruments
        nifty = get_fno_instruments()
        nfut = nifty.front_future(today) if nifty.ready(today) else None
        if nfut is None:
            _p(False, "NIFTY book not ready -- skipped (not blocking)")
        else:
            mixed = await kite.get_quote([nfut.token, fut.token])
            _p(
                nfut.token in mixed and fut.token in mixed,
                f"both legs returned ({len(mixed)}/2)",
            )
    except Exception as exc:
        _p(False, f"mixed batch errored: {exc} (not blocking)")

    # ---- 4. SENSEX futures 5-min volume quality -----------------------
    print("4. SENSEX fut 5-min bars volume quality")
    frm = (now - timedelta(days=7)).strftime("%Y-%m-%d 09:15:00")
    bars = await kite.get_intraday_by_token(
        fut.token, frm, now.strftime("%Y-%m-%d %H:%M:%S"), interval="5minute",
    )
    got_bars = bars is not None and not bars.empty
    results.append(_p(got_bars, f"bars fetched rows={0 if not got_bars else len(bars)}"))
    if got_bars and "volume" in bars:
        nz = float((bars["volume"] > 0).mean())
        results.append(_p(
            nz > 0.5,
            f"non-zero-volume bars={nz * 100:.0f}% "
            "(<=50% => leave SENSEX signal_enabled=False)",
        ))
    else:
        results.append(_p(False, "no volume column"))

    # ---- 5. daily historicals for RV ----------------------------------
    print("5. interval=day historicals (RV sources)")
    frm_d = (now - timedelta(days=45)).strftime("%Y-%m-%d")
    d = await kite.get_intraday_by_token(fut.token, frm_d, now.strftime("%Y-%m-%d"), interval="day")
    results.append(_p(
        d is not None and not d.empty and len(d) >= 21,
        f"SENSEX fut dailies rows={0 if d is None or d.empty else len(d)} (need >=21)",
    ))
    for name, tok in INDEX_TOKENS.items():
        di = await kite.get_intraday_by_token(tok, frm_d, now.strftime("%Y-%m-%d"), interval="day")
        _p(
            di is not None and not di.empty,
            f"index token {name}={tok} dailies rows="
            f"{0 if di is None or di.empty else len(di)} (bonus, not blocking)",
        )

    # ---- 6. BFO option OI populates -----------------------------------
    print("6. BFO option-quote OI")
    from fno_chain import take_chain_snapshot
    snap = await take_chain_snapshot(kite, book, now)
    if snap is None:
        results.append(_p(False, "chain snapshot unavailable"))
    else:
        with_oi = sum(1 for q_ in snap.quotes.values() if q_.oi > 0)
        results.append(_p(
            with_oi > 0,
            f"{with_oi}/{len(snap.quotes)} contracts report OI>0",
        ))

    print()
    if all(results):
        print("ALL BLOCKING CHECKS PASSED -- P3 (SENSEX) may proceed; flip "
              "SPECS['SENSEX'].signal_enabled only if check 4 passed too.")
        return 0
    print("BLOCKING FAILURES above -- SENSEX stays analytics-only/disabled.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
