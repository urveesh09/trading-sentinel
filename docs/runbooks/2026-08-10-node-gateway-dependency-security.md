# Node gateway dependency security note - 2026-08-10

Scope: Dev `node-gateway/server` only. Production was not modified. This
bounded tranche upgraded only `express` 4.19.2 -> 4.22.2 and
`express-session` 1.18.0 -> 1.19.0, retaining exact version pins. No major
upgrade was applied to Kite Connect, Telegram, node-cron, or uuid.

## Verification

- `npm audit --omit=dev --json` before: **33** production findings
  (7 low, 9 moderate, 12 high, 5 critical).
- `npm audit --omit=dev --json` after: **25** production findings
  (2 low, 9 moderate, 9 high, 5 critical).
- Clean Node 20 Alpine install and full Jest suite: **22 suites passed, 1
  skipped; 274 tests passed, 4 skipped**. The suite reported its two known
  forced-exit handles (token-restore timeout and Telegram polling TCP handle),
  but no test failure or Express/session compatibility regression.

The upgraded Express chain now resolves `body-parser` 1.20.6, `cookie` 0.7.2,
`path-to-regexp` 0.1.13, `qs` 6.15.3, `send` 0.19.2, and `serve-static` 1.16.3.
The session chain resolves `cookie` 0.7.2 and `on-headers` 1.1.0.

## Remaining production audit findings

Direct dependencies requiring deliberately deferred major upgrades:

- **critical**: `kiteconnect` 3.2.0; npm proposes 5.3.0 (major).
- **moderate**: `node-telegram-bot-api` 0.65.0; npm proposes 1.2.0 (major).
- **moderate**: `node-cron` 3.0.3; npm proposes 4.6.0 (major).
- **moderate**: `uuid` 10.0.0; npm proposes 14.0.1 (major).

Remaining transitive findings, exactly as reported by the post-upgrade audit:

- **critical (4):** `crypto-js` (Kite), `form-data` and `request`
  (Telegram), and `tar` (the `connect-sqlite3`/`sqlite3` build chain).
- **high (9):** `axios` and `ws` (Kite); `lodash` (Telegram); plus
  `brace-expansion`, `cacache`, `ip-address`, `make-fetch-happen`, `node-gyp`,
  and `sqlite3` in the SQLite native-install chain.
- **moderate (6):** `@cypress/request`, `@cypress/request-promise`,
  `request-promise-core`, `qs`, and `tough-cookie` through Telegram, plus
  `follow-redirects` through Kite.
- **low (2):** `@tootallnate/once` and `http-proxy-agent` in the SQLite
  native-install chain.

## Upgrade blockers and next boundary

Kite 5.x requires a separate broker-SDK compatibility review around quote,
order, GTT, authentication, and error-shape behavior. Telegram 1.x replaces
the legacy request stack and needs polling/webhook, retry, and dead-letter
regression coverage. node-cron 4.x needs schedule/startup behavior validation;
uuid 14.x needs CommonJS/ESM and generated-ID compatibility validation.
SQLite build-chain remediation should be assessed separately with
`connect-sqlite3`/`sqlite3` native ABI and persistence tests. Those changes are
outside this non-major tranche and were intentionally not forced by
`npm audit fix --force`.
