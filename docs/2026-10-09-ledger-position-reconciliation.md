# Ledger versus position-store mismatches explained (Oct 9 audit item 11)

The Oct 9 audit lists four divisions whose ledger close rows and closed
position rows disagree. Each gap was matched row by row against a read-only
query of Production's `/data/cache.db`. No row was changed. Ledger cash stays
the record. This page explains the gaps; it does not restate the totals.

| Division | Ledger / positions | P&L delta | Cause |
| --- | --- | --- | --- |
| MOMENTUM (live) | 24 / 22 | −₹10.79 | THELEELA (+₹7.45) and LATENTVIEW (+₹3.33) were closed at 08:26 and 08:57 UTC on Jul 20, then booked again by the 09:45 UTC (15:15 IST) square-off. Both pairs were later relabelled SYSTEM→MOMENTUM by the Jul 26 repair. |
| PENNY_PAPER | 29 / 28 | −₹3.71 | AMDIND position 74 was booked at +₹3.71 on Aug 31 (ledger 137), then closed for real at +₹5.45 on Sep 1 (ledger 139). |
| EDGE_PAPER | 19 / 9 | −₹119.71 | Ten closes from Jul 1–20 (NECCLTD … JINDWORLD) have ledger rows but no `positions` rows. Their sum is exactly +₹119.71. |
| EDGE_LIVE | 11 / 5 | −₹39.17 | Six closes from Jul 1–2 (NECCLTD … IRISDOREME), sum +₹39.16 (rounding), ledger only. |

## Can it happen again?

- **Double bookings (Momentum, Penny).** Both are from before the fixes:
  - `[LEDGER-INTEGRITY 2026-07-26]`: the Momentum close and auto-square
    paths write the ledger only when their `UPDATE positions` closed
    exactly one row.
  - Penny exits are booked once per confirmed exit (`confirmed_exit:*` notes
    from Sep 1).
  - No gap has appeared after Sep 1 in any division.
- **EDGE rows without positions.** These come from the first weeks of the EDGE
  engine, before its legs were written to `positions` (the first EDGE
  position row is Jul 30). Later EDGE closes reconcile one to one.

## What the numbers mean

- The four ledgers carry these phantom or unmatched amounts: Momentum
  +₹10.78, Penny paper +₹3.71, EDGE paper +₹119.71, EDGE live +₹39.16.
- The position stores are the per-trade truth for those rows.
- The ledger is left as written, because rewriting historical cash is not
  remediation. A reader comparing books should subtract these amounts, or use
  the position totals, for these divisions.
