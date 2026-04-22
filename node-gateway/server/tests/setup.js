/**
 * Jest global setup - loads test env before any require() runs.
 * This file MUST be required first via setupFiles in jest.config.js.
 */
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '.env.test'), override: true });
