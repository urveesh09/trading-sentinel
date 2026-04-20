const express = require('express');
const session = require('express-session');
const SQLiteStore = require('connect-sqlite3')(session);
const path = require('path');

const config = require('./config');
const security = require('./middleware/security');
const { httpLogger, logger } = require('./middleware/logger');

const app = express();

// Trust reverse proxy (Nginx) for correct IP and rate limiting
app.set('trust proxy', 1);

// 1. Logging Middleware
app.use(httpLogger);

// 2. Security Headers & Strict CORS
app.use(security.securityHeaders);
app.use(security.corsOptions);

// 3. Telegram Webhook Route (Must be parsed specifically for the bot)
if (config.TELEGRAM_MODE === 'webhook' && config.TELEGRAM_WEBHOOK_PATH) {
  const telegram = require('./services/telegram');
  app.post(
    config.TELEGRAM_WEBHOOK_PATH, 
    security.limiters.webhook, 
    security.verifyTelegramWebhook, 
    express.json({ limit: '5kb' }), 
    (req, res) => {
      telegram.bot.processUpdate(req.body);
      res.sendStatus(200);
    }
  );
}

// 4. Body Parser for Standard APIs
app.use(express.json({ limit: '10kb' }));

// 5. Secure Session Management (SQLite Persistent)
/*const DATA_DIR = config.NODE_ENV === 'production' ? '/data' : path.join(__dirname, '../data');
app.use(session({
  store: new SQLiteStore({ dir: DATA_DIR, db: 'sessions.db' }),
  secret: config.SESSION_SECRET,
  resave: false,
  saveUninitialized: false,
  cookie: {
    httpOnly: true,
    secure: config.NODE_ENV === 'production',
    sameSite: 'strict',
    maxAge: 8 * 60 * 60 * 1000 // 8 hours
  },
  rolling: true // Refresh session maxAge on activity
}));
// 5. Secure Session Management (SQLite Persistent)
const DATA_DIR = '/data'; // CRITICAL FIX: Hardcoded to the Docker persistent volume

app.use(session({
  store: new SQLiteStore({ dir: DATA_DIR, db: 'sessions.db' }),
  secret: config.SESSION_SECRET,
  resave: false,
  saveUninitialized: false,
  cookie: {
    httpOnly: true,
    secure: config.NODE_ENV === 'production',
    sameSite: 'lax', // CRITICAL FIX: Changed to 'lax' so Zerodha redirects don't drop the cookie
    maxAge: 8 * 60 * 60 * 1000 // 8 hours
  },
  rolling: true // Refresh session maxAge on activity
}));*/
// 5. Secure Session Management (SQLite Persistent)
const DATA_DIR = config.NODE_ENV === 'production' ? '/data' : path.join(__dirname, 'session_store');
const fs = require('fs');

// Ensure the directory exists so SQLite doesn't crash trying to make the file
if (!fs.existsSync(DATA_DIR)){
    fs.mkdirSync(DATA_DIR, { recursive: true });
}

app.use(session({
  store: new SQLiteStore({ dir: DATA_DIR, db: 'sessions.db' }),
  secret: config.SESSION_SECRET,
  resave: false,
  saveUninitialized: false,
  cookie: {
    httpOnly: true,
    secure: config.NODE_ENV === 'production',
    sameSite: 'lax', 
    maxAge: 8 * 60 * 60 * 1000 
  },
  rolling: true 
}));
// 6. API Routes
app.use('/api/auth', security.limiters.auth, require('./routes/auth'));
app.use('/api/signals', security.limiters.signals, require('./routes/signals'));
app.use('/api/orders', security.limiters.orders, require('./routes/orders'));
app.use('/api/token', security.limiters.token, require('./routes/token'));
app.use('/api/proxy', require('./routes/proxy'));
app.use('/api/health', require('./routes/health'));
app.use('/api/internal', require('./routes/internal'));


// 7. React Static File Serving
//app.use(express.static(path.join(__dirname, '../public')));
//app.get('*', (req, res) => {
 // res.sendFile(path.join(__dirname, '../public/index.html'));
//});
// 7. React Static File Serving
//app.use(express.static(path.join(__dirname, '../client/dist')));
//app.get('*', (req, res) => {
//  res.sendFile(path.join(__dirname, '../client/dist/index.html'));
//});

// 7. React Static File Serving
app.use(express.static(path.join(__dirname, 'public')));
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public/index.html'));
});

// 8. Global Error Handler
app.use((err, req, res, next) => {
  const statusCode = err.statusCode || 500;
  const type = err.type || 'internal_error';
  const clientMessage = err.clientMessage || 'An unexpected error occurred.';

  if (statusCode >= 500) {
    logger.error({ err, req_id: req.id, type }, 'Unhandled Exception');
  } else {
    // 4xx errors are logged as warnings
    logger.warn({ err_msg: err.message, req_id: req.id, type }, 'Client Error');
  }

  res.status(statusCode).json({
    error: type,
    message: clientMessage
  });
});

module.exports = app;
