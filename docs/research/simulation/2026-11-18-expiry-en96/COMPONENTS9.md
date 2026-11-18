# Round 9 components — good part, harmful part, what removal does, interactions

**Basis:**
- Full-grid, independent-session comparisons against each family's reference on 197 already-studied NIFTY expiries.
- EN105's ablations at the boundaries where components existed.
- Labelled post-score diagnostics (`post9.json`).

Descriptive only: nothing here is a qualified result. "Removed" means the component switched back to EN87's version.

## Component ledger

| Component | Good part | Harmful part | Without it (back to EN87) | Interactions seen | Retain? |
|---|---|---|---|---|---|
| **OI agreement gate** (EN87, at E03 clocks) | Removes 30 E03 parents worth −₹2,601 (13 winners, 17 losers); robust to basket width, anchor and aggregation (12/18 identical ledgers) | Only modestly better than random retention matched by time bin (31st of 40); 2026 still −₹2,451; about 0.13 parents per expiry | E03_env: 3,006 / 2,246, wallet −3,445 | It replaces timing poorly: with looser E03 timing (EN108) it cuts losses but never pays | **Retain** as the base mechanism (development lead only) |
| Moderate threshold band (p60–70, L10–15) | +2 to +5 parents, up to +₹8/session; extra parents net positive in the best cells | Not every neighbour helps; the H20 vs H40 history window flips some cells | EN87 (p80) | It is the signal gene EN105 picked at boundaries 160/180 (inner +₹3,097, outer +₹153) | Retain as a range to test, not a cell |
| Stricter threshold (p90) or long lookback (30 min) | — | Removes winners: −₹7.8 to −24.2/session | — | — | **Reject** |
| Frozen-13:00 basket | — | Loses 1–2 winners (−₹5 to −7.5/session) | — | — | Reject |
| Price-extension cap (EN98) | Untested: the grid sat below every E03 entry (2.5–7 ATR) | — | — | — | Needs a corrected registration (3–6 ATR) |
| Patient entry (EN99 confirm/reclaim) | Fills 3–8 arms at sometimes better prices | Most arms expire, and the unfilled ones were winners (+₹161 to +219 per lot at +8 min) | Immediate entry | A deterministic 3-minute delay happened to be fine (+₹1.2/session) but its neighbours lose (EN81 pattern again) | **Reject** |
| **Nearer contract, one lot** (EN100 nearest / min-friction) | +₹5,600 on the same 25 clocks; beats EN87's three far lots within the same ₹2,500 | Bigger stop losses (−₹450 to −635 on three parents); +₹4,459 of the gain is 2025 | EN87 one lot 3,735 / 3,063 | Needs the legacy admission rule: without it, 5 extra parents lose −₹3,700 (EN92's failure). EN105 boundary 180: contract gene outer +₹1,420, inner −₹263 | **Retain** as a mechanism; test on unseen sessions |
| Friction cap 0.05 on the legacy pick | — | Halves activity and loses (1,966 / 1,755) | — | — | Reject |
| **Hold 12 minutes** (EN101) | +₹9.8/session as a fixed rule; the evidence-gated version adds 4 parents (+₹2,136) | 16–24 minutes give back (24 min with OI permission: 1,795 / 1,573) | 8-minute clock | Random extensions are flat, so the evidence is not doing much beyond the clock | Retain the 12-minute question; reject long holds |
| OI-opposition exit (EN102) | — | Never fires: d·S15 on the fixed entry basket stays positive in every EN87 hold | Identical | Redundant with the entry gate | Reject (inert) |
| Price-damage exit without OI | — | Cuts winners: −₹8 to −27/session | — | — | **Reject** |
| Scout plus add (EN103) | Lower initial exposure | About ₹900 lost to the reserved add room and ₹1,000–1,450 to the late add; ⅓ = ½ under three lots | EN87 full size | — | **Reject** for informed parents |
| Delayed agreement (EN104 structure-holds) | Recovers 1–2 good parents (+₹1,155 to +1,444) | p70 admits losers; "E03 still signals" never happens | EN87 | Unconditional +1-minute entries look good (+₹2,090) but +3/+5 lose | Unresolved (support too thin) |
| Second sources (EN107) | OI ∨ basis p70 adds 4 parents (+₹674) | Synthetic forward and basis alone, and all AND rules, remove winners; SENSEX cannot form thresholds | OI only | — | **Reject** |
| Looser E03 timing (EN108) | — | Even gated: −₹22 to −60/session; ungated −₹29,137 (efficiency 0.5) | E03 efficiency 0.7 | OI does not substitute for timing | **Reject** |
| Graded size (EN109) | — | Weak-agreement lots lose (−₹831); smaller agreeing lots lose winner size | Full size on agreement | No dose-response in payoffs by z | **Reject** |
| **Higher first target, +150%** (EN110) | +₹5,000–6,000 in all six stop/keep cells, from 4 trades whose runner trail gave back a spike | Rests on 4 trades in 2024–25; 2023/2026 unchanged; target +60% loses | E03 target +100% | Not information-specific: the same 4 trades gain identically in E03_env (post-score). Native E03.2 +₹4,729, but its wallet halt is unchanged; EN55 +₹419; SENSEX 0 | **Retain** as an exit question for unseen sessions |
| OI layer on native E03.2 (EN106) | VETO: +₹1.1/session; on EN55, VETO +₹920 | GATE and TILT remove E03.2's winners (14:30–15:00 and 2× puts) | Native E03.2 | Native money and the 15:00 window dilute the gate (bridge cells) | **Reject** as a way to beat E03.2 |

## Interactions (EN105, boundary 180 — the only boundary with three components)

| Gene | Mean change, inner window | Mean change, outer block |
|---|---:|---:|
| Signal (EN96 5/60/40) | +₹3,097 | +₹153 |
| Management (EN101 12/info/0.2) | +₹1,874 | 0 |
| Contract (nearest, 0.10) | −₹263 | +₹1,420 |

- Genotypes passing the constraints: 48 of 64, with 8 distinct ledgers.
- The selected genotype 100110 made +₹500 in an outer block where EN87 lost −₹873, on 3 against 2 parents. This is too little to call an interaction.
- At the other five boundaries no gene had a passing component, so no interaction is measurable. This is the honest limit of combining parts of a book that trades once every eight expiries.

## What this means for the next round

1. Keep EN87's entry exactly as it is; filters and timing changes only lose its winners.
2. The money questions now sit on the exit and the contract:
   - should a strong informed winner be half-sold at +100%;
   - should the one lot be nearer the money?

   Both depend on a few large trades and must be judged on sessions never studied.
3. Do not spend more slots on threshold tuning, baskets, scouts, patient entries, OI exits, second sources or looser timing for this signal; each family here answered that.
