# Penny clock correction review — November 8, 2026

Problem: review the other agent corrections to 6af2f08 against Production evidence. Accept settled exchange timestamps after trading ends and expiring hypothetical no-evidence decisions, while preventing fabricated completeness, inconsistent volume clocks and false auction evidence. Smart LTP is not a verified indicative auction-price source.

Files/contracts: preserve the other agent current uncommitted clock fixes and report. Review penny_auction_forward.py, focused tests, config, guide, active plan, checklist and atlas. All edits in Dev. Read-only Production export uses mode=ro/query_only snapshots. No provider quote/order, Breeze, push, deployment or Production write. Retain old receipts and tests.

Acceptance: reproduce reported packet ages/pre-open observations directly; no positive volume with a last trade at/before the decision; no complete portfolio P&L after NO_EVIDENCE even once later trades close; retries do not erase real OPEN exposure; ordinary matching evidence follows the current published auction clock; Smart forward trading stays off until a verified indicative source while the observer continues. Test proposed changes and the new regressions. Record background suite source limits rather than claiming its results cover later edits. Run affected suite and appropriate engine checks once final source is frozen.

Rollout/rollback: independent Smart forward-entry switch default false, visibility capture remains. No old-store schema migration. NO_EVIDENCE frees only conditional paper reservations, with incomplete capital path and null complete P&L explicit. Original baseline untouched. Revert this Dev commit or disable the forward collector to roll back. Forward profitability and actual fills stay unqualified.

Completed: read-only Production evidence export, correction review, additional safeguards, 43 direct tests, 1,065 affected-suite tests, separate synthetic exercise, source-drift check, and atlas. Delivery is a local Dev commit with immediate documentation consistency verification. Preserve unrelated staged/unstaged owner and partner work.
