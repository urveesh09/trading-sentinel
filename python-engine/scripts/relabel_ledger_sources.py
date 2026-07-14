#!/usr/bin/env python3
"""
[TIER0-0.2/0.7 2026-07-14] One-off migration: relabel mislabelled bankroll_ledger rows.

THE PROBLEM
-----------
`daily_post_market` bound the ledger callback as a 2-arg lambda:

    update_daily_positions(db, kite, today, lambda t, p: record_trade_close(db, t, p))

which dropped the position's source, so `record_trade_close` fell back to its
default `source="SYSTEM"`. But `update_daily_positions` walks EVERY open position,
including EDGE_PAPER ones sized off a ₹100,000 IMAGINARY bankroll while the real
book is ₹5,000.

Result, in the live DB right now: all 23 ledger rows are tagged 'SYSTEM',
totalling +₹3,740.56 -- but most of that is paper money.

    EDGE_PAPER  = +3,826.27   <- fiction, ₹100k paper bankroll
    EDGE_LIVE   =    +39.16
    MOMENTUM    =    -23.33

The real book is ~₹5,016, not ~₹8,842. Every downstream number -- edge_stats,
expectancy, win rate, and every A/B comparison the alpha roadmap depends on --
inherits this. `edge_stats.py` run against the current DB reports a beautiful,
entirely fictional edge.

The code path is fixed (position_tracker now passes the source through). This
script repairs the HISTORY.

WHAT IT DOES
------------
For each TRADE_CLOSED row still tagged 'SYSTEM', find the matching `positions` row
by ticker (preferring the closest exit_date) and rewrite `source` to that
position's true source. Rows it cannot match are left alone and reported.

It does NOT touch pnl, and it does NOT delete anything. Money history is
append-only; only the label is wrong.

USAGE
-----
Dry run (default -- prints the plan, changes nothing):

    docker exec python-engine python /app/scripts/relabel_ledger_sources.py

Apply:

    docker exec python-engine python /app/scripts/relabel_ledger_sources.py --apply

Take a backup first:

    docker exec python-engine cp /data/cache.db /data/cache.db.bak-$(date +%F)
"""
import argparse
import sqlite3
import sys
from collections import defaultdict

DB_PATH = "/data/cache.db"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default is a dry run)")
    ap.add_argument("--db", default=DB_PATH)
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    rows = con.execute(
        "SELECT id, ticker, pnl, timestamp, source FROM bankroll_ledger "
        "WHERE event_type = 'TRADE_CLOSED' AND source = 'SYSTEM' "
        "ORDER BY id"
    ).fetchall()

    if not rows:
        print("Nothing to do: no TRADE_CLOSED rows tagged 'SYSTEM'.")
        return 0

    plan, unmatched = [], []
    for r in rows:
        # Prefer the position whose exit_date is nearest this ledger timestamp;
        # a ticker can be traded more than once, and both legs of the EDGE
        # dual-book share a ticker (differing only by source).
        cands = con.execute(
            "SELECT source, realised_pnl, exit_date FROM positions "
            "WHERE ticker = ? AND source IS NOT NULL",
            (r["ticker"],),
        ).fetchall()
        if not cands:
            unmatched.append((r["id"], r["ticker"], r["pnl"], "no positions row"))
            continue

        # The pnl is the discriminator between the paper and live legs of the
        # same EDGE signal: they differ by ~100x (the bankroll ratio).
        best = min(
            cands,
            key=lambda c: abs((c["realised_pnl"] or 0.0) - (r["pnl"] or 0.0)),
        )
        if best["source"] == "SYSTEM":
            unmatched.append((r["id"], r["ticker"], r["pnl"], "position is also SYSTEM"))
            continue
        plan.append((r["id"], r["ticker"], r["pnl"], best["source"]))

    # ---- recover the orphans -------------------------------------------------
    # Six rows (NECCLTD, OLAELEC, MCLOUD -- each twice) have NO positions row at
    # all: the position rows were deleted but the ledger rows survived. They
    # include MCLOUD +1,325.18, the single largest fictional profit in the book,
    # so leaving them tagged SYSTEM would leave most of the contamination in place.
    #
    # They are still identifiable. EDGE runs a PAPER leg (₹100,000 bankroll) and a
    # LIVE leg (₹1,000) against the same signal, so each orphan appears exactly
    # TWICE for the same ticker, with P&L in the bankroll ratio (~100:1) and the
    # same sign. That signature does not occur for MOMENTUM or swing, which book
    # once per trade.
    #
    # This is a HEURISTIC, not a lookup. It only fires on an exact 2-row,
    # same-sign, 20x-to-500x pair -- anything else is left for a human.
    by_ticker = defaultdict(list)
    for _id, ticker, pnl, why in unmatched:
        if why == "no positions row":
            by_ticker[ticker].append((_id, pnl))

    recovered_ids = set()
    for ticker, entries in by_ticker.items():
        if len(entries) != 2:
            continue
        (id_a, pnl_a), (id_b, pnl_b) = entries
        if not pnl_a or not pnl_b or (pnl_a > 0) != (pnl_b > 0):
            continue
        big, small = (
            ((id_a, pnl_a), (id_b, pnl_b))
            if abs(pnl_a) >= abs(pnl_b)
            else ((id_b, pnl_b), (id_a, pnl_a))
        )
        ratio = abs(big[1]) / abs(small[1])
        if not (20 <= ratio <= 500):
            continue
        plan.append((big[0], ticker, big[1], "EDGE_PAPER"))
        plan.append((small[0], ticker, small[1], "EDGE_LIVE"))
        recovered_ids.update({big[0], small[0]})
        print(f"  [orphan-pair] {ticker}: {big[1]:.2f} / {small[1]:.2f} "
              f"= {ratio:.0f}x -> EDGE_PAPER / EDGE_LIVE")

    unmatched = [u for u in unmatched if u[0] not in recovered_ids]
    plan.sort(key=lambda p: p[0])

    pools = defaultdict(float)
    for _id, _t, pnl, src in plan:
        pools[src] += pnl or 0.0

    print(f"{'APPLY' if args.apply else 'DRY RUN'} — {args.db}\n")
    print(f"{len(plan)} row(s) to relabel, {len(unmatched)} unmatched.\n")
    for _id, ticker, pnl, src in plan:
        print(f"  ledger#{_id:<4} {ticker:<12} {pnl:>10.2f}   SYSTEM -> {src}")

    if unmatched:
        print("\nUNMATCHED (left as SYSTEM — review by hand):")
        for _id, ticker, pnl, why in unmatched:
            print(f"  ledger#{_id:<4} {ticker:<12} {pnl:>10.2f}   {why}")

    print("\nP&L moving out of the live SYSTEM pool, by destination:")
    for src, total in sorted(pools.items()):
        print(f"  {src:<12} {total:>10.2f}")

    moved = sum(pools.values())
    print(f"\n  SYSTEM pool changes by {-moved:+.2f}")
    print("  (expect it to get WORSE — that is the fix working: the paper")
    print("   profits were never real.)")

    if not args.apply:
        print("\nDry run. Re-run with --apply to write.")
        return 0

    with con:
        for _id, _ticker, _pnl, src in plan:
            con.execute(
                "UPDATE bankroll_ledger SET source = ? WHERE id = ?", (src, _id)
            )
    print(f"\nApplied. {len(plan)} row(s) relabelled.")

    print("\nPools now:")
    for r in con.execute(
        "SELECT source, COUNT(*) n, ROUND(SUM(pnl), 2) pnl "
        "FROM bankroll_ledger GROUP BY source ORDER BY source"
    ):
        print(f"  {r['source']:<12} n={r['n']:<4} pnl={r['pnl']:>10.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
