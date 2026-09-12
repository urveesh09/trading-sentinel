# Production evidence inventory and CAS follow-up

## Read-only inventory, September 12

Production application containers python-engine and node-gateway were exited with code 0; agent exited with code 137. nginx was restarting. These are point-in-time observations, not a diagnosis of why the operator/services stopped them. No application service was started or modified.

Inspected the existing production_trading-sentinel_trading_data Docker volume mounted read-only at /evidence, with networking disabled in a disposable helper container. The /evidence/research directory contained operational-fno, collection-runs, quotes and contract-masters.

- Four archived contract-master manifests.
- September 10 compressed quote journal and its manifest.
- September 11 open quote journal.
- Zero partner-public-inputs JSON captures at this archive root.

This inventory does not revalidate the older journals' contents or prove there is no alternate archive elsewhere. It does establish that the new full-policy CLI has no retained public captures at the inspected operational root. We cannot run a complete observed session replay from that root now. No qualified outcome or start date for partner tips follows from the new code tests.

## Next development and operational sequence

1. Verify deployment identity and finish passive collection of the exact public inputs plus contemporaneous candidate chain/profile bundles. Public capture code exists in Dev; absence in this Production archive must remain visible.
2. Verify per-session collection attempts, failures and expected-vs-observed coverage. A list of supplied valid files is insufficient proof of a complete session.
3. Complete candidate receipt/decision timing support: do not require accidental timestamp equality or backdate a fetch to make it causal.
4. Perform release acceptance, then promote through GitHub when authorized. Existing stopped services are not automatically restarted by this research task.
5. Run the offline CLI on genuine new captures. Preserve NO_SETUP, NO_FILL and UNRESOLVED results; qualify only from reviewed costed held-out evidence.

## CAS: verified scope and engineering implications

NSE's current CAS page states that phase 1 covers cash stocks with derivative contracts. It lists CAS at 15:15–15:35, equity derivatives at 09:15–15:40, and non-CAS cash continuous trading until 15:30. CAS does not allow stop-loss or iceberg orders. Source: https://www.nseindia.com/static/products-services/closing-auction-session (checked September 12).

Engineering follow-up: inventory hard-coded session times and distinguish exchange session, security eligibility, broker square-off and Sentinel's own earlier exit policy. Preserve the partner's existing 15:15 deadline until a separately reviewed policy changes it. Do not treat CAS as an option strategy or as proof of an edge. First test session classification and data availability; auction-imbalance research requires a supported feed and its own evidence.

SEBI's original circular: https://www.sebi.gov.in/legal/circulars/jan-2026/introduction-of-closing-auction-session-cas-in-the-equity-cash-segment-and-certain-modifications-in-the-pre-open-auction-session_99122.html

No trading, delivery, session-time or Production configuration changes were made during this inventory.
