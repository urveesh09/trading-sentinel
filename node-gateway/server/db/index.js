const Database = require('better-sqlite3');
const fs = require('fs');
const path = require('path');
const config = require('../config');

// Ensure /data volume exists and is writable (Hard fail if not)
const DATA_DIR = config.NODE_ENV === 'production' ? '/data' : path.join(__dirname, '../../data');

try {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }
  fs.accessSync(DATA_DIR, fs.constants.W_OK);
} catch (err) {
  console.error(` FATAL: Persistent data directory ${DATA_DIR} is not writable. Exiting.`);
  process.exit(1);
}

// Initialize Databases
const signalsDb = new Database(path.join(DATA_DIR, 'signals.db'));
const appDb = new Database(path.join(DATA_DIR, 'app.db'));

// Enforce WAL mode on all connections
signalsDb.pragma('journal_mode = WAL');
appDb.pragma('journal_mode = WAL');

// Run Migrations (Idempotent)
const schema = fs.readFileSync(path.join(__dirname, 'schema.sql'), 'utf8');
signalsDb.exec(schema);

// We attach app_state logic to appDb
appDb.exec(`
  CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
  );
`);

module.exports = {
  signalsDb,
  appDb
};
