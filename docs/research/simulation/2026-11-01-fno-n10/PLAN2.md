# N10 round two: come back small, and earn only where it pays

Written after round one's verdict, before any round-two book is scored. Round one stays failed on the record (`results.json`). All four years are seen and round one has now been read, so this round is more searching on the same data: discipline, not an exam. Dev research only.

## What round one showed

**The earned lot does not replace the entry lot.** Earned in place of N08's entry-time second lot: 1,51,406 against 2,02,284. The value is in the entry: N08's entry-time second lots made +76,704 where earned lots made about +30,000 to +41,000. The random control agrees: the add hurts random entries in every year (helped 1, 2, 2 and 3 of 10), so a trade that has reached +1R has no market-wide tendency to continue. My first idea was wrong.

**The earned lot pays only on top of a two-lot trade.** In HYBRID_C, on trades already holding two lots: -1,437 / +11,844 / 0 / +15,004 = +25,411 (17 lots). On one-lot trades: -6,072 / +111 / -1,866 / +948 = -6,879 (41 lots). A two-lot trade is one where the volatility reading is on and the premium is cheap. This split is found by looking, so it is a hypothesis.

**N09.1's account result sits on a cliff.** This is the largest finding.

| Book | Free cash above the floor, end of 2023 | Jan 1, 2024 | Trades in 2024 | One account ends |
|---|---:|---|---:|---:|
| EARN_WC | 5,284 | taken | 25 | 4,05,525 |
| HYBRID_C | 4,941 | taken | 22 | 4,37,141 |
| N09.1 CUSHION | 4,688 | refused at 12:36 (needs 4,731.54), taken at 12:37 (needs 4,669.65) | 17 | 3,84,310 |
| LADDER_WC | 4,668.98 | refused by 67 paise | 3 | 2,16,481 |
| EARN_WVC | 4,594 | refused | 3 | 2,16,922 |

N09.1's headline rests on a margin of Rs 18.45 and a 95-paise move in one minute. The Jan 1 trade won about Rs 3,900 and that freed the account. **A floor that never lowers is a permanent stop that arrives a little earlier and a little more quietly.** In a year with no edge the book drains its free cash until nothing can be funded. Whether it escapes is decided by rupees.

Round one's check 6 was therefore partly a coin flip. That doesn't change round one's verdict, because the rule stands; it changes what a sound check has to look like.

**The full-premium reserve is about 3.5 times the worst loss seen.** The worst of 243 one-lot trades lost 28.3% of its premium, because the 25% backstop holds intraday in this candle model. Real fills may be worse, so the reserve stays: it is what makes the floor a guarantee.

## The rules

### WATCH: how the account comes back

When an entry is refused because no lot can be funded above the floor, the book keeps watching its own rules on paper. It may lower the floor by **one small slice** only if:

- the last 20 paper trades, closed strictly before now, made money together (N09's reading, one lot, brakes off, N08's signals);
- at least 20 paper trades have closed since the last slice, so the same evidence can't be spent twice;
- the new floor is not below **75% of the account's best closed equity**.

One slice is **5% of the best closed equity**. At Rs 2.5 lakh: Rs 2,12,500, then 2,00,000, then 1,87,500, and no lower. The floor rises again with new highs as before, and it keeps every other N09.1 rule: full premium reserved, never lowered for any other reason, never reset by a calendar. The native 15% halt is replaced by this floor for WATCH books alone.

Why this and not N09's restart: a restart grants a fresh 15% each time and reached Rs 1,28,867 when 2023 repeated four times. WATCH has a fixed bottom, and each step buys only a lot or two. It is the owner's "smart, not blocking": it stands aside when it has been wrong, keeps checking itself, and returns small when the evidence returns. **Any change to the live 15% stop stays the owner's decision.**

### THIRD: the earned lot, only where it pays

N09.1's entry (one or two lots by the volatility reading), and one earned lot at +1R, with round one's stop and exits, only when the first entry already holds **two lots**. X stays 1.0: X = 0.75 looked better in round one, and picking it would be choosing on what I saw.

**Planned risk with the earned lot may not exceed Rs 5,000,** never scaled up by the risk multiplier: the owner's own limit (O31d). This is stated after seeing that HYBRID_C's worst trade, -6,405 on Apr 10, 2026, had planned risk 6,147 under a limit the multiplier had raised to 7,175. So it is partly fitted to one seen trade, and it is disclosed as such.

## Books

| Name | Entry | Earned lot | Account |
|---|---|---|---|
| R2_CW | N09.1 CUSHION | none | WATCH |
| R2_THIRD_C | N09.1 CUSHION | THIRD | no WATCH |
| **R2_THIRD_CW = N10B** | N09.1 CUSHION | THIRD | WATCH |

**Neighbours:** X = 0.75 and 1.25 on R2_THIRD_CW, fresh years. Paper window 10 and 30, slice 2.5% and 10%, one account.

**The cliff test:** one account at extra cost 10% lower and 10% higher, for N09.1 CUSHION, R2_CW and R2_THIRD_CW. A sound account rule shouldn't depend on a few rupees. The cost shift is only a way to move 2023's ending a little.

**Double cost:** R2_CW and R2_THIRD_CW. **Stress:** all 256 whole-year orderings on N09.1's causal proxy at one lot, with WATCH added, its paper evidence strictly before each entry.

## Verdict for N10B, fixed now

N10B passes only if R2_THIRD_CW meets all of these. No threshold moves afterwards.

1. Four-year fresh sum above N08's 2,02,284.
2. Worst day no larger than N09.1's 6,127.
3. Worst annual closed fall no larger than N08's 15.08%.
4. 2023 net no worse than N08's -37,581.
5. 2024, 2025 and 2026 each positive, and at least two at or above N09.1's (76,294 / 46,738 / 99,870).
6. One account at or above N09.1's 3,84,310 at the base cost **and** at both cost shifts.
7. Double extra cost: four-year sum at or above N09.1's 1,52,165.
8. Plateau: X = 0.75 and 1.25 each above N09.1's 1,90,218, and all four WATCH neighbours end one account at or above 3,84,310.
9. Without its five largest winners, the sum is at or above N09.1's without its own five.
10. Stress: worst ending at or above Rs 1,87,500, and median at or above N09.1 CUSHION's on the same proxy.

**Checks 3 and 4 are looser than round one's,** against N08 instead of N09.1. The reason is stated before scoring: part of N09.1's smaller 2023 loss is the trap itself. A book that keeps its ability to come back can lose a little more in the bad year. That is a real cost and will be reported against N09.1 as well.

**R2_CW has its own smaller question:** does WATCH alone remove the cliff? It passes if one account stays within 5% of its base result across both cost shifts while N09.1 CUSHION does not, and check 10 holds.

**Reported, not gates:** paired weekly t, bootstrap, CSCV across round one and round two together, what WATCH did (each slice's date, evidence, and the trades after it), what THIRD's lots made, and how many books have now been tried.

Passing makes N10B a candidate on seen years. NIFTY 2022 and new sessions remain the only fair tests. Nothing here changes anything live, and Monday's real-money test stays at one lot.
