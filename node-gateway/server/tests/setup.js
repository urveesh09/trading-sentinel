/**
 * Jest global setup - loads test env before any require() runs.
 * This file MUST be required first via setupFiles in jest.config.js.
 */
const path = require('path');
// Load the test fixture first: it intentionally carries development-safe
// defaults used by several integration tests.
require('dotenv').config({ path: path.join(__dirname, '..', '.env.test'), override: true });

// market-hours normally refreshes its fallback holiday calendar from the
// Python engine when the module is loaded. A gateway unit/integration suite
// must not make that background network request: it can outlive Jest and
// produce a post-test log, while contributing no assertion coverage. The
// gateway module honours this flag only in a Jest worker, so it cannot
// suppress the production refresh by configuration accident. Do not replace
// NODE_ENV here: the development-safe fixture is intentionally used by
// gateway configuration tests.
process.env.MARKET_HOURS_TEST_DISABLE_ENGINE_FETCH = '1';
