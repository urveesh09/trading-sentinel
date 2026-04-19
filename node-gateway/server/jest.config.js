/** @type {import('jest').Config} */
module.exports = {
  testEnvironment: 'node',
  testMatch: ['**/tests/**/*.test.js'],
  setupFiles: ['./tests/setup.js'],
  // Increase timeout for async tests
  testTimeout: 10000,
  // Run tests serially to avoid DB contention
  maxWorkers: 1,
};
