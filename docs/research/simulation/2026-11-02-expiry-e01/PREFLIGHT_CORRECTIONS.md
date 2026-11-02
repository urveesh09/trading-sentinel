# Pre-score adapter corrections; no candidate scored

- Windows asyncio creates an internal loopback socket before async main.
  Blocking every socket connect at import prevented that loop from starting.
  The guard now activates INSIDE async main, before market replay/source load.
  It still refuses all network during the replay; providers are recorded fakes.
- The first Oct13 historical comparison used15:45:00 rather than the actual
  recorded reconciliation instant15:45:00.043296. Money matched; settlement
  event timestamps differed. Replay now binds the archived post-session
  reconciliation clock. Original failed pilot output remains retained.
- Oct6 source predates EXECUTION_VERSION and bank_pending. Missing version is
  explicitly legacy-unversioned. Five bank_pending fields were added by later
  migration with DEFAULT0; only None versus exactly0 is normalized by the
  separate comparator. Original strict mismatch output remains. No event,
  quantity, price, fee or P&L was normalized. All eight/95 legs match.
- The uncommitted freeze-round1.json draft bound source/data but omitted
  effective non-secret budget/fee settings. Before any candidate score, the
  active freeze is strengthened to freeze-round1-v2.json, binding those settings
  and the original draft bytes. Draft source/configuration copies stay private.
  No policy, threshold, candidate, dataset, gate or acceptance rule changed.

First committed candidate source/config/input freeze is the active v2, not a
retrospective preregistration. All eight sessions were already seen regardless.
