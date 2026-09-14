/**
 * Jest global setup - loads test env before any require() runs.
 * This file MUST be required first via setupFiles in jest.config.js.
 */
const path = require('path');
// [WORKFLOW-J.5] Force test-mode so __resetHolidaysForTest's
// gated seam is exercisable. The original setup.js used
// process.env.NODE_ENV to gate the test-only path, but
// `process.env.NODE_ENV` may not be set when this file
// evaluates (npm test vs jest internals). Setting it here is
// idempotent -- production never loads this file.
process.env.NODE_ENV = process.env.NODE_ENV || 'test';
require('dotenv').config({ path: path.join(__dirname, '..', '.env.test'), override: true });
