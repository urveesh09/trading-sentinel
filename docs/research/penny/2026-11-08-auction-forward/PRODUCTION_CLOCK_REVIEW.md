# Penny auction forward: checked against Production quotes (November 8, 2026)

This reviews the first version of `penny_auction_forward.py` (commit `6af2f08`) against what Kite really returned in Production. Production was read only (`398d44a`, sqlite `mode=ro`). Nothing was written there.

## What Production shows

**Post-close packets are minutes old.** The overnight post-close probe (`edge_overnight_postclose_probe`) holds 10 real picks from Nov 5–6, each read at 15:32 (CLOSE) and 16:03 (POST).
- At 16:03 the packet `timestamp` was 182 to 612 seconds old on all 10. The exchange sends nothing after the session, so an old packet is the final one.
- The first version required a packet under 30 seconds old at 16:03. All 10 fail that.
- At 15:32 the packets were 35–41 s old. They carried a 15:31 broadcast on every name.

**The close is known from 15:31.** At 15:32, `last_price` equalled the official daily close (`ohlcv_cache`) on 6 of the 6 names that can be checked (Nov 5). That includes ORIENTALTL and VERTOZ, which had no post-close trade.

**Post-close volume is small.**

| Pick | Post-close shares | Pick | Post-close shares |
|---|---:|---|---:|
| GNRL | 1,490 | LAL | 670 |
| NOVAAGRI | 30 | MFML | 1,100 |
| OPTIFIN | 1,501 | MTNL | 13,832 |
| ORIENTALTL | 0 | TTML | 9,691 |
| RUSHIL | 22 | VERTOZ | 0 |

These are POST minus CLOSE volume.

**The 09:07 pre-open quote does not show the auction.**
- In the Smart V3 store (`sv3_preopen`), `last_price` equalled the previous close on 125 of 125 quotes (Nov 5–6). SV3 recorded `indicative_moved: 0` on both days.
- That held for GEEKAYWIRE, which opened 4% down, and for GNRL, which opened 9.8% down.
- So no gap can be seen at 09:07. Nothing is eligible, and neither SV3_PREOPEN nor the forward Smart arms can ever pick.

## The faults in the first version, and the Dev fixes

| | Fault | Fix |
|---|---|---|
| 1 | **16:03 rule.** The 30-second packet rule applied after the close, so every POST_END read failed. Each overnight entry went UNRESOLVED, and the Smart close arm could never sell after the close. | **Quiet segments.** In a segment that sends nothing new before the read, a packet only has to be today's, from its start time on, and not after the read: from 09:00 in the 09:12–09:15 auction buffer, and from 15:30 in the post-close book and after 16:00. The 30-second rule still applies to the 09:30–15:20 bid exits. |
| 2 | **UNRESOLVED never ended.** No code left that status. It kept its cash and an overnight slot for good, and any one UNRESOLVED Smart row set the paired cash to 0 for good. A job missed at 09:12 or 16:03 left rows PENDING, with the same effect. One bad read stopped a book permanently. | **NO_EVIDENCE.** A decision whose only evidence phase has passed becomes `NO_EVIDENCE`, whether the read was bad or never ran. It stays in the counts, has no modeled P&L, and frees its cash and slot. Rows written by the first version as `UNRESOLVED` read the same way. |
| 3 | **15:51 trade.** The 15:51 decision needed a trade in the 15:50–15:51 minute and a packet under 30 seconds old, though the price is already known. | **No trade needed.** The decision packet must be settled since 15:30 and traded today. |
| 4 | **No later trade.** A post-close book with no trade after the decision was treated as missing evidence. | **Zero capacity.** It is measured zero capacity: REFUSED `no_later_postclose_volume`. |
| 5 | **09:12 trade window.** MATCH accepted only a 09:10–09:12 trade and a packet under 30 seconds old. Kite's stamp for the auction trade has not been seen, and nothing trades in the buffer. | **Before 09:15.** Any trade today before 09:15 is the auction's trade, and the packet rule from fix 1 applies. |
| 6 | **Hidden pre-open price.** Nothing reported that the pre-open price is invisible. | **Recorded.** Each Smart day records `preopen_price_moved`, and `comparison()["smart_preopen_price"]` reports `visible`. |

`complete_modeled_net` is now null until at least one decision has closed. With nothing closed, there is no P&L to report. It also stays null while any position is open, as before.

## Replay of the 10 real post-close quotes

Each name was run alone with a ₹12,500 ticket. The 15:32 packet stands in for the 15:51 decision (the real 15:51 packets were not stored), and the 16:03 packet is the real one.

| | Old rules | New rules |
|---|---|---|
| Decision at 15:51 | Not made: the packet is too old and has no 15:50 trade | Made for all 10 |
| 16:03 result | All 10 rejected, so every row would be UNRESOLVED for good | MTNL OPEN 138 of 463 shares, TTML OPEN 96 of 313; 6 REFUSED below the 25% minimum, 2 REFUSED with no later trade |

**At 1% of later volume, 8 of 10 real picks cannot enter.** If the order instead took every later share (it would be first in the queue when the book is empty), GNRL, OPTIFIN and MFML would fill in full and LAL would fill 62%. The 1% share was the first version's choice; it is not measured.

## Still unverified (first live sessions)

- **The 09:12 packet.** It is not yet known whether Kite's quote shows `ohlc.open` and the auction volume before 09:15, or what `last_trade_time` the auction trade carries. The first MATCH `runs` payloads will show it.
- **Post-close depth.** Does the 15:51 depth show the post-close book's resting orders at the close? The `runs` payloads keep the raw packets with depth. If they do, a time-priority fill (resting sells first, then later volume after the buyers ahead) can replace the 1% guess.
- **The Smart arms.** They make no picks while the pre-open price is invisible. The price-independent design (preselected limits at 98% of the close) already failed in the Nov 4 research. Another decision source would need new research first.

## Verification

- **New checks:** `tests/test_penny_auction_forward.py` has 35. The 7 new ones fail on the first version and pass now:
  - the real Nov 6 MTNL and TTML packets;
  - an auction packet from before the buffer;
  - a missed MATCH job;
  - a missed 16:03 job;
  - an unobserved entry freeing its slots;
  - no later trade;
  - pre-open visibility.
- **Rewritten check:** one invalid-auction-data check now expects `NO_EVIDENCE` with its cash freed.
- **Penny group:** penny, overnight, Smart, scheduler and surface tests: 1,290 passed, 1 skipped, exit 0.

Dev only, a local commit. It is paper only and has no order path. Classic MIS/CNC entries default off in `6af2f08`. That is the owner's call before any promotion.
