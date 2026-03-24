const pino = require('pino');
const pinoHttp = require('pino-http');
const crypto = require('crypto');
const config = require('../config');
const { sanitise } = require('../utils/sanitise');

// Base logger instance
const logger = pino({
  level: config.LOG_LEVEL,
  formatters: {
    level: (label) => ({ level: label })
  },
  timestamp: pino.stdTimeFunctions.isoTime
});

// HTTP Request Logger Middleware
const httpLogger = pinoHttp({
  logger,
  genReqId: (req) => req.id || crypto.randomUUID(),
  customLogLevel: (req, res, err) => {
    if (res.statusCode >= 500 || err) return 'error';
    if (res.statusCode >= 400) return 'warn';
    return 'info';
  },
  serializers: {
    req: (req) => ({
      id: req.id,
      method: req.method,
      url: req.url,
      ip: req.remoteAddress
    }),
    res: (res) => ({
      statusCode: res.statusCode
    }),
    err: pino.stdSerializers.err
  },
  // Ensure we sanitize req bodies if they get logged
  customProps: (req, res) => ({
    body: req.body ? sanitise(req.body) : undefined
  })
});

module.exports = { logger, httpLogger };
