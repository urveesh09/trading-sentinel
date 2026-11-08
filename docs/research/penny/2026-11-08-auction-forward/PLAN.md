# Penny auction forward development — November 8, 2026

## Problem
Existing Smart V3 fixes quantity after clearing and measures capacity after continuous trading starts. Overnight V2/V3 rebase 15:20 assumptions to official prices. Neither is executable fill evidence. Classic MIS/CNC retirement is recommended but not implemented.

## Scope and contracts
Dev only. Preserve the existing V3/overnight books, research and owner edits. Add an independent broker-free forward book in penny_auction_forward.py. Freeze Smart orders before 09:08 with limit-price own-cash sizing, using observed matching volume before 09:15. Compare a 09:30 displayed-bid exit and a post-close-price exit from identical entries. Freeze overnight V2/V3 candidate inputs at the existing 15:20 decision, fund fixed quantities at a fresh post-close decision, assess only subsequent supported-session volume, and observe the following auction before continuous trading. Every entry remains a conditional capacity model, actual_fill UNKNOWN. Missing evidence retains reserved cash and withholds complete P&L. No hindsight resizing, invented auction sale or broker order.

Use existing costs, Smart candidate rules and overnight V2/V3 ordering. Reuse existing quote responses for entry hooks, bounded new scheduled batches for matching/post-close/bid phases, independent sibling SQLite store and additive authenticated experiment fields. Current Classic MIS/CNC entries default retired with separate reversible entry switches; exits, Smart controls and shadow evaluations remain available. No F&O change, Breeze call, Production edit, push or deployment.

## Acceptance
Tests cover funded immutable quantities, exact session/provider/receipt clocks, quote acquisition crossing a deadline, missing/reset auction volume, limit refusal, partial depth, lower-circuit/no-bid carries, fees, losses reducing capital, identical Smart entry arms, restart/idempotency/concurrency, no order capability, source integration, retirement preserving exits/shadows, route compatibility and calendar gates. Replay the new functions on synthetic observed tapes and audit archived quote availability without claiming a fresh historical strategy exam. Run affected Penny/scheduler/API tests, then the required engine suite once. Record failures and exact results.

## Rollout and rollback
New forward paper flag PENNY_AUCTION_FORWARD_ENABLED defaults true, requires enabled parent Penny books and ordinary calendar/token gates. No existing stores migrated or settings files activated. Rollback new collection with false; preserve outstanding evidence. Restore Classic entries separately through PENNY_CLASSIC_MIS_ENTRIES_ENABLED / PENNY_CLASSIC_CNC_ENTRIES_ENABLED, both default false. Promote only through GitHub on owner instruction.

## Remaining work
Implementation, source review, full engine suite (6,314 passed / 4 skipped / exit 0), focused mechanics, concurrency exercise and atlas regeneration are complete. Guide/active plan/checklist include the Dev behavior and rollback. Development and verification are complete; delivery is a local Dev commit only. Forward profitability/fill qualification remains pending real observations. Preserve the older uncommitted Smart/Classic reports without staging them as this task's work.
