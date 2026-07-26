#!/usr/bin/env python3
"""Second-stage ledger repair: division attribution.

The first repair (repair_phantom_ledger_2026_07_26.py) fixed the MONEY -- it
reversed the 8 fabricated TRADE_CLOSED rows and cleared the circuit breaker. This
one fixes WHO THE TRADES BELONG TO, which the money repair deliberately left
alone.

Two distinct problems in the same rows:

1. MISATTRIBUTION. record_trade_close() defaulted to source="SYSTEM", and three
   momentum close paths never passed a source (_close_momentum_position,
   auto_square_momentum, POST /positions/close). So every SYSTEM row in the
   ledger actually belongs to a MOMENTUM position. Swing was credited with 12
   losing trades it never took; swing has in fact never closed a trade. Ledger
   ids 28-31 are genuine momentum closes from 2026-07-20 and are relabelled.

2. PHANTOM ROWS STILL COUNT AS TRADES. Ids 33-45 were the daily re-closes of two
   positions that had already exited on 07-20. Their money is already reversed by
   matching ADJUSTMENT rows, but they are still event_type='TRADE_CLOSED', so
   promotion_report and division_breakdown count them as 8 real trades. They were
   never trades. Their event_type becomes TRADE_VOID, which every statistic
   filters out, while the row survives as evidence.

Money is unchanged by both steps. nifty_bankroll sums SYSTEM and MOMENTUM
together and ignores event_type, so relabelling within that pair and renaming an
event type both net to exactly zero. What changes is which division each book is
judged on -- the thing the promotion ladder reads.

  python3 repair_ledger_attribution_2026_07_26.py --db /data/cache.db --dry-run
  python3 repair_ledger_attribution_2026_07_26.py --db /data/cache.db --apply
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime

# Genuine momentum closes wrongly tagged SYSTEM. Pinned by primary key so this
# can never touch a row it was not reviewed against.
MISATTRIBUTED_IDS = [28, 29, 30, 31]

# Re-closes of positions that had already exited on 2026-07-20. Money already
# reversed; these must stop counting as trades.
PHANTOM_TRADE_IDS = [33, 34, 36, 37, 39, 40, 44, 45]

VOID_EVENT = "TRADE_VOID"


def _die(msg: str) -> None:
    print(f"ABORT: {msg}", file=sys.stderr)
    sys.exit(1)


def _fetch(con, ids):
    marks = ",".join("?" * len(ids))
    rows = con.execute(
        f"SELECT id, timestamp, ticker, event_type, source, pnl "
        f"FROM bankroll_ledger WHERE id IN ({marks}) ORDER BY id", ids,
    ).fetchall()
    if len(rows) != len(ids):
        _die(f"expected ids {ids}, found {sorted(r['id'] for r in rows)}")
    return rows


def _division_totals(con):
    return dict(con.execute(
        "SELECT source, COUNT(*) FROM bankroll_ledger "
        "WHERE event_type='TRADE_CLOSED' GROUP BY source"
    ).fetchall())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/data/cache.db")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    already = con.execute(
        "SELECT COUNT(*) FROM bankroll_ledger WHERE event_type=?", (VOID_EVENT,)
    ).fetchone()[0]
    if already:
        _die("this repair has already been applied (TRADE_VOID rows present)")

    mis = _fetch(con, MISATTRIBUTED_IDS)
    for r in mis:
        if r["source"] != "SYSTEM" or r["event_type"] != "TRADE_CLOSED":
            _die(f"id {r['id']} is {r['event_type']}/{r['source']}, expected TRADE_CLOSED/SYSTEM")

    phantoms = _fetch(con, PHANTOM_TRADE_IDS)
    for r in phantoms:
        if r["event_type"] != "TRADE_CLOSED":
            _die(f"id {r['id']} is {r['event_type']}, expected TRADE_CLOSED")

    print(f"DB: {args.db}\n")
    print(f"--- {len(mis)} genuine MOMENTUM closes mislabelled SYSTEM -> MOMENTUM ---")
    for r in mis:
        print(f"  id={r['id']:<3} {r['timestamp'][:10]}  {r['ticker']:<11} {r['pnl']:>9.4f}")
    print(f"\n--- {len(phantoms)} phantom rows TRADE_CLOSED -> {VOID_EVENT} ---")
    for r in phantoms:
        print(f"  id={r['id']:<3} {r['timestamp'][:10]}  {r['ticker']:<11} {r['pnl']:>9.4f}")

    before = _division_totals(con)
    print(f"\ntrade counts before: {before}")
    projected = dict(before)
    projected["SYSTEM"] = projected.get("SYSTEM", 0) - len(mis) - len(phantoms)
    projected["MOMENTUM"] = projected.get("MOMENTUM", 0) + len(mis)
    print(f"trade counts after:  {projected}")
    print("\nMoney is unchanged: nifty_bankroll sums SYSTEM+MOMENTUM and ignores")
    print("event_type, so neither step moves a rupee.")

    if args.dry_run:
        print("\nDRY RUN -- nothing written.")
        return

    backup = f"{args.db}.bak-attribution-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.copy2(args.db, backup)
    print(f"\nbackup written: {backup}")

    with con:
        marks = ",".join("?" * len(MISATTRIBUTED_IDS))
        con.execute(
            f"UPDATE bankroll_ledger SET source='MOMENTUM', "
            f"notes=COALESCE(notes,'')||' [relabelled SYSTEM->MOMENTUM 2026-07-26: "
            f"momentum close mis-tagged by record_trade_close default]' "
            f"WHERE id IN ({marks})", MISATTRIBUTED_IDS,
        )
        marks = ",".join("?" * len(PHANTOM_TRADE_IDS))
        con.execute(
            f"UPDATE bankroll_ledger SET event_type=?, "
            f"notes=COALESCE(notes,'')||' [voided 2026-07-26: re-close of a position "
            f"already exited 2026-07-20; money reversed by matching ADJUSTMENT]' "
            f"WHERE id IN ({marks})", [VOID_EVENT] + PHANTOM_TRADE_IDS,
        )

    print(f"\ntrade counts after:  {_division_totals(con)}")


if __name__ == "__main__":
    main()
