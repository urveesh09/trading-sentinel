#!/usr/bin/env python3
"""One-time prod repair for the 2026-07-21..24 phantom-position artifacts.

Context (see docs/post-mortem/2026-07-23_24-trading-days-audit.md):

THELEELA and LATENTVIEW were fully exited on 2026-07-20 but kept
status='CLOSED_T1' with exit_date set. get_open_positions() treated them as
open, so auto_square_momentum re-squared both at 15:15 on 07-21, 07-22, 07-23
and 07-24 -- placing real Zerodha orders AND booking a fabricated TRADE_CLOSED
row each time, because its UPDATE matched zero rows while record_trade_close()
ran regardless.

This script repairs the *accounting*. Three things:

  1. Terminalise the two position rows (CLOSED_T1 -> CLOSED_MANUAL) so they can
     never be picked up again, even by a caller that ignores exit_date.
  2. Reverse the 8 fabricated TRADE_CLOSED rows with explicit compensating
     entries. It does NOT delete them: the ledger is append-only history and
     the fabricated rows are evidence. Each reversal is tagged so the pair is
     legible, and bankroll_after is recomputed forward from the first touched
     row so the running balance stays consistent.
  3. Insert a CB_RESET so CB_CONSECUTIVE_LOSSES stops counting the fabricated
     streak (8 losses, all phantom; the two real closes before them were wins).

The code fix in af545a0 stops any NEW fabrication. This only cleans up what
already landed.

Safe by default: --dry-run prints the plan and writes nothing. --apply takes a
timestamped backup of the DB first and refuses to run twice (it checks for its
own reversal tag).

  python3 repair_phantom_ledger_2026_07_26.py --db /data/cache.db --dry-run
  python3 repair_phantom_ledger_2026_07_26.py --db /data/cache.db --apply
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime

# The 8 fabricated rows, identified in the audit. Pinned by primary key so this
# script can never touch a row it was not reviewed against.
PHANTOM_LEDGER_IDS = [33, 34, 36, 37, 39, 40, 44, 45]

PHANTOM_POSITIONS = [
    ("THELEELA", "2026-07-20T07:41:04.853151+00:00"),
    ("LATENTVIEW", "2026-07-20T08:11:17.156510+00:00"),
]

REVERSAL_TAG = "phantom_reversal_2026-07-26"
CB_RESET_TAG = "CB_RESET after phantom-ledger repair 2026-07-26"


def _die(msg: str) -> None:
    print(f"ABORT: {msg}", file=sys.stderr)
    sys.exit(1)


def _fetch_phantom_rows(con: sqlite3.Connection) -> list[sqlite3.Row]:
    marks = ",".join("?" * len(PHANTOM_LEDGER_IDS))
    rows = con.execute(
        f"SELECT id, timestamp, event_type, ticker, source, pnl, "
        f"       bankroll_after, notes "
        f"FROM bankroll_ledger WHERE id IN ({marks}) ORDER BY id",
        PHANTOM_LEDGER_IDS,
    ).fetchall()
    if len(rows) != len(PHANTOM_LEDGER_IDS):
        found = sorted(r["id"] for r in rows)
        _die(f"expected ledger ids {PHANTOM_LEDGER_IDS}, found {found}")
    for r in rows:
        # Guard against repairing the wrong DB or a shifted schema.
        if r["event_type"] != "TRADE_CLOSED":
            _die(f"ledger id {r['id']} is {r['event_type']}, expected TRADE_CLOSED")
        if r["source"] != "SYSTEM":
            _die(f"ledger id {r['id']} has source {r['source']}, expected SYSTEM")
        if r["pnl"] >= 0:
            _die(f"ledger id {r['id']} pnl={r['pnl']} is not a loss -- refusing")
    return rows


def _already_repaired(con: sqlite3.Connection) -> bool:
    n = con.execute(
        "SELECT COUNT(*) FROM bankroll_ledger WHERE notes LIKE ?",
        (f"%{REVERSAL_TAG}%",),
    ).fetchone()[0]
    return n > 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/data/cache.db")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    if _already_repaired(con):
        _die("this repair has already been applied (reversal tag present)")

    rows = _fetch_phantom_rows(con)
    total = sum(r["pnl"] for r in rows)

    print(f"DB: {args.db}")
    print(f"\n--- {len(rows)} fabricated TRADE_CLOSED rows to reverse ---")
    for r in rows:
        print(f"  id={r['id']:>3}  {r['timestamp']}  pnl={r['pnl']:>10.4f}")
    print(f"  {'':>28}  TOTAL={total:>10.4f}  (reversal: {-total:+.4f})")

    # Positions to terminalise.
    print("\n--- position rows to terminalise ---")
    for ticker, entry_date in PHANTOM_POSITIONS:
        p = con.execute(
            "SELECT ticker, status, exit_date, realised_pnl FROM positions "
            "WHERE ticker=? AND entry_date=? AND source='MOMENTUM'",
            (ticker, entry_date),
        ).fetchone()
        if p is None:
            _die(f"position {ticker} @ {entry_date} not found")
        print(f"  {p['ticker']:<12} status={p['status']} -> CLOSED_MANUAL "
              f"(exit_date={p['exit_date']})")

    bankroll_before = con.execute(
        "SELECT bankroll_after FROM bankroll_ledger ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    print(f"\nbankroll_after (latest row): {bankroll_before:.4f}")
    print(f"after repair:                {bankroll_before - total:.4f}")
    print("\nAlso inserts: 1 x CB_RESET row (clears the fabricated loss streak)")

    if args.dry_run:
        print("\nDRY RUN -- nothing written.")
        return

    backup = f"{args.db}.bak-phantom-repair-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.copy2(args.db, backup)
    print(f"\nbackup written: {backup}")

    now_iso = datetime.utcnow().isoformat() + "+00:00"
    running = bankroll_before

    with con:
        # 1. Compensating entries, one per fabricated row, so each pair is
        #    traceable. Append-only: the originals stay as evidence.
        for r in rows:
            before = running
            running -= r["pnl"]          # pnl is negative -> running rises
            con.execute(
                "INSERT INTO bankroll_ledger "
                "(timestamp, event_type, ticker, source, pnl, "
                " bankroll_before, bankroll_after, notes) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (now_iso, "ADJUSTMENT", r["ticker"], "SYSTEM", -r["pnl"],
                 before, running,
                 f"{REVERSAL_TAG}: reverses fabricated TRADE_CLOSED id={r['id']} "
                 f"(phantom auto-square of an already-exited position)"),
            )

        # 2. Terminalise the position rows.
        for ticker, entry_date in PHANTOM_POSITIONS:
            con.execute(
                "UPDATE positions SET status='CLOSED_MANUAL' "
                "WHERE ticker=? AND entry_date=? AND source='MOMENTUM'",
                (ticker, entry_date),
            )

        # 3. CB_RESET so the consecutive-loss counter stops at this point.
        con.execute(
            "INSERT INTO bankroll_ledger "
            "(timestamp, event_type, source, pnl, "
            " bankroll_before, bankroll_after, notes) "
            "VALUES (?,?,?,?,?,?,?)",
            (now_iso, "CB_RESET", "SYSTEM", 0.0, running, running, CB_RESET_TAG),
        )

    print("\n--- applied ---")
    for r in con.execute(
        "SELECT id, event_type, source, pnl, bankroll_after, notes "
        "FROM bankroll_ledger ORDER BY id DESC LIMIT 10"
    ):
        note = (r["notes"] or "")[:52]
        print(f"  id={r['id']:>3} {r['event_type']:<12} pnl={r['pnl']:>10.4f} "
              f"after={r['bankroll_after']:>10.4f}  {note}")
    print(f"\nfinal bankroll_after: {running:.4f}")


if __name__ == "__main__":
    main()
