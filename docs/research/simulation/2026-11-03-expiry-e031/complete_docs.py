"""Add the implementation receipt without including unrelated owner doc edits."""
from pathlib import Path
import checkpoint as C

NOTE='''## November 3 — E03.1 defensive paper candidate complete (Dev; off, not deployed)

Report: `docs/EXPIRY_RESEARCH_E031.md`; contracts/remaining:
`docs/research/simulation/2026-11-03-expiry-e031/PLAN.md` and `IMPLEMENTATION_PLAN.md`.
- New `expiry-e031-v1` / E031 variant: E03 entry/runner/reserves unchanged,
  initial stop 35%, pre-runner trigger floor 1.1x after a 50% peak gain. Own
  `.expiry-e031.db`, `EXPIRY_E031_SHADOW_ENABLED=false`; policy saved per ticket.
- SMALL fitted gain: continuous ordinary +12,426.71 vs E03 +11,956.35; adverse
  +11,497.60 vs +11,114.83. Six ordinary incremental days, ex-largest +288.71.
  Worst ordinary day -478.01 vs -568.26. SEVERE LOSES 3,234.08; not qualified.
  2024/2025 seen, 2023 protected. 55 sweeps + 149 new genome combinations;
  FOLLOW and adaptive selectors rejected; no further tuning after 0c7f414 freeze.
- Verification: 99 original E03 histories exact; 391 native position replays /
  407 sale slices zero mismatches; 43 focused checks; full engine 6,118 passed,
  4 skipped, 53 warnings, 694.61 seconds, exit 0. Existing warnings and Penny
  fixture shutdown logging error retained. Atlas regenerated (295 modules).
  Commands/results: study `verification.json`. Tests establish mechanics only.
- Dev only, implementation commit/push receipt follows. No .env edit or existing
  store migration; separate E031 DB only on future enable/tests. No broker,
  message, primary ledger, Production, N11/N11T, A/B/C or E02/E03 rule changes.
  Existing owner work preserved; Production 06bed07 unchanged. Stop floors can gap.
- Remaining: separately authorized GitHub rollout and new paired forward paper
  tickets/execution evidence, at least 20 closed before review, both book and
  matched-ticket comparisons. No automatic promotion or C replacement.

'''.encode('utf-8')

def main():
    for name in ('SYSTEM_GUIDE.md','NEXT_AGENT_PLAN.md','HANDOVER_CHECKLIST.md'):
        prefix=C.own_prefix(name)
        # Correct an escaped backtick in the earlier own preface, not owner text.
        prefix=prefix.replace(b'\x0cinalists-freeze.json',b'`finalists-freeze.json`')
        assert not any(c<32 and c not in (9,10,13) for c in prefix)
        original=(C.HERE/'_local'/(name+'.initial')).read_bytes()
        (C.ROOT/'docs'/name).write_bytes(NOTE+prefix+original)
    print('E031_COMPLETION_DOCS_UPDATED; owner original tails preserved')

if __name__=='__main__':main()
