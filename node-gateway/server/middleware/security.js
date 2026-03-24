const helmet = require('helmet');
const cors = require('cors');
const rateLimit = require('express-rate-limit');
const crypto = require('crypto');
const config = require('../config');

// 1. Helmet with strict CSP

// 1. Helmet with strict CSP (Adjusted for HTTP testing)
const securityHeaders = helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"],
      imgSrc: ["'self'", "data:"],
      connectSrc: ["'self'"],
      upgradeInsecureRequests: null, // CRITICAL: Stops forcing HTTPS
    }
  },
  hsts: false // CRITICAL: Disables strict HTTPS caching
});
/*const securityHeaders = helmet({
  contentSecurityPolicy: {
    defaultSrc: ["'self'"],
    scriptSrc: ["'self'"],
    styleSrc: ["'self'", "'unsafe-inline'"],
    imgSrc: ["'self'", "data:"],
    connectSrc: ["'self'"]
  },
  hsts: { maxAge: 31536000, includeSubDomains: true }
});*/

// 2. Strict CORS
const corsOptions = cors({
  origin: (origin, callback) => {
    if (!origin || config.ALLOWED_ORIGINS.includes(origin)) {
      callback(null, true);
    } else {
      callback(new Error('Not allowed by CORS'));
    }
  },
  credentials: true,
  methods: ['GET', 'POST']
});

// 3. Rate Limiters
const createLimiter = (maxReq, windowMs = config.RATE_LIMIT_WINDOW_MS) => rateLimit({
  windowMs,
  max: maxReq,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'rate_limit', message: 'Too many requests, please try again later.' }
});

const limiters = {
  auth: createLimiter(10, 15 * 60 * 1000), // 10 req / 15 min
  signals: createLimiter(60, 60 * 1000),   // 60 req / 1 min
  orders: createLimiter(20, 60 * 1000),    // 20 req / 1 min
  token: createLimiter(10, 60 * 60 * 1000),// 10 req / 1 hour
  webhook: createLimiter(100, 60 * 1000),  // 100 req / 1 min
  default: createLimiter(100, 60 * 1000)
};

// 4. Webhook & Internal API Signature Verifiers
const verifyInternalApi = (req, res, next) => {
  const authHeader = req.headers['authorization'];
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ error: 'unauthorized', message: 'Missing token' });
  }
  const token = authHeader.split(' ')[1];
  
  try {
    const isMatch = crypto.timingSafeEqual(
      Buffer.from(token),
      Buffer.from(config.INTERNAL_API_SECRET)
    );
    if (!isMatch) throw new Error();
    next();
  } catch {
    return res.status(401).json({ error: 'unauthorized', message: 'Invalid token' });
  }
};

const verifyTelegramWebhook = (req, res, next) => {
  const secret = req.headers['x-telegram-bot-api-secret-token'];
  if (!secret) return res.status(401).json({ error: 'unauthorized', message: 'Missing secret token' });
  
  try {
    const isMatch = crypto.timingSafeEqual(
      Buffer.from(secret),
      Buffer.from(config.TELEGRAM_WEBHOOK_SECRET)
    );
    if (!isMatch) throw new Error();
    next();
  } catch {
    return res.status(401).json({ error: 'unauthorized', message: 'Invalid secret token' });
  }
};

module.exports = {
  securityHeaders,
  corsOptions,
  limiters,
  verifyInternalApi,
  verifyTelegramWebhook
};
