# E03.2 investigation — plan, written before any morning score (November 3, 2026)

Owner request (November 3): build an E03.2 that clearly beats E03 and E03.1, or
learn why it can't. Full autonomy, try other perspectives, iterate, a genome is
allowed. Earn much more while keeping losses small.

Starting Dev checkout `374384f` (E03.1 docs). E03 `d85a690` and E03.1 `65cccb7`
are disabled paper variants, not deployed. Production is read-only. Other agents'
uncommitted working changes are left untouched; only this folder and named files
are staged.

## What is already used up, and what is not

- **Afternoons (13:00-15:00) of the 105 NIFTY expiry days in 2024/2025 are fully
  seen.** E02 (2,746 rule evaluations), E03 (34 book runs plus diagnostics) and
  E03.1 (204 candidates) all chose rules there. Nothing more fitted there is a test.
- **Mornings (09:30-13:00) of the same 105 days have never been scored by any
  expiry option rule.** E02's genome only allowed starts of 13:00 or 13:30
  (`2026-11-03-expiry-e02/search.py`). E03's census and surface start at 13:00.
  E03.1 starts at 12:59. The surface read morning *index* volatility only, as an
  input. The same agent has seen index paths of some of these days, so the morning
  is not a pure blind exam, but no morning option price has picked a rule.
- No 2026 same-day-expiry option minute chain exists (`expiry-year/README.md`).
  The ten-second 2026 export holds one opening-ATM strike per day, too few for
  E03's strike choice. Days before expiry have about eight strikes near the money,
  outside E03's Rs 5-20 band. SENSEX has no full chain. **No new download.** NIFTY
  2023 stays protected: every query stays inside the 2024/2025 tapes.

## Phase 1 — the morning test (frozen in `freeze-morning.json` before scoring)

The question: does E02's entry, unchanged, also find edge in the morning? If yes,
the book gets more good tickets without any new parameter. That is the only
direction that can add a lot of money without a fitted rule or a bigger loss.

Arms, each its own Rs 25,000 book with E02's brakes, decisions only from 09:30 to
13:00 (`start=570`, `end=780`); a ticket bought before 13:00 keeps its own exits.
Every other setting is the frozen rule, unchanged:

| Arm | Rule |
|---|---|
| `M_E02` | E02 R3 (one lot, sells at 2x), four-strike cap |
| `M_E03` | E03 (three lots in Rs 1,250, half sold at 2x, runner) |
| `M_E031` | E03.1 (35% stop, 1.1x floor after a 50% peak gain) |

Scored once, both years, ordinary / adverse / severe fills, independent years and
one continuous 2024-2025 book, plus 40 random-entry seeds (same windows, same
signal count per day, same exits; only the minute and direction are drawn).

**Pass (fixed now): `M_E03` earns more than zero in each year at ordinary AND
adverse fills; is positive in each year without its best day (ordinary); has no
day worse than -Rs 1,250; and beats the median random seed in each year.** The
severe-fill result is reported and is not part of the pass, as for E03.

- If the morning passes, Phase 2 builds an all-day book. Two designs, both
  reported: **A** shares E03's two tickets and Rs 2,500 a day across 09:30-15:00
  (no extra money at risk); **B** gives the morning its own two tickets and
  Rs 2,500 (at most Rs 5,000 reserved a day). B is chosen only if its worst day
  stays at or above -Rs 1,250 and it is positive without the best day in each
  year at adverse fills; otherwise A.
- If the morning fails, the failure is recorded and the morning is not traded.
  A morning-specific refit would be in-sample and is labelled as such.

## Phase 2+ — other ideas (all in-sample, every trial recorded in `trials.csv`)

1. **House-money roll:** at E02's 2x sale, sell the whole ticket and spend part of
   its profit (never the original cost) on a further-OTM strike in the same direction.
2. **Add only when risk-free:** a second ticket while the first one's stop is at or
   above its cost.
3. **Size with equity:** the ticket reserve as a share of the book's cash, so profit
   compounds and a losing run shrinks the ticket.
4. **A third ticket a day.**
5. A bounded genome (at most 400 new combinations, two seeds) over these mechanisms,
   scored by the **worst** of (year x fill) results without the best day, with a
   leave-one-year-out check of how much a pick decays on the other year.

## Acceptance for an E03.2 candidate

Improves E03.1 in each year at ordinary and adverse fills; positive without the
best day in each year; worst day no worse than -Rs 1,250; continuous-cash realized
drawdown no worse than Rs 2,500; random-entry control beaten in each year; the
gain not confined to one setting (coarse neighbours). Severe fills reported. A
stop is a trigger, not a price. Anything else is a learning, not a candidate.

## Rollout / rollback

Research is Dev only. A runtime variant, if any, is a new disabled paper variant
in `expiry_e02.py` with its own DB, cash and flag (default false), lab-to-paper
parity zero mismatches, focused tests and the full suite. Promotion is the
owner's GitHub decision; rollback is the flag or a revert. Docs (guide, plan,
checklist, atlas) are updated with each implementation commit.
