/** @type {import('jest').Config} */
module.exports = {
  testEnvironment: 'node',
  testMatch: ['**/tests/**/*.test.js'],
  setupFiles: ['./tests/setup.js'],
  // Increase timeout for async tests
  testTimeout: 10000,
  // Run tests serially to avoid DB contention
  maxWorkers: 1,
  // [WORKFLOW-J.5] Always run as a test process so the
  // __resetHolidaysForTest seam in utils/market-hours.js
  // can be exercised. Production code is unaffected.
  globals: {},
};
