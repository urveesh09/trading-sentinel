/**
 * Middleware to protect routes that require an authenticated active session.
 */
const requireSession = (req, res, next) => {
  if (!req.session || !req.session.authenticated) {
    return res.status(401).json({
      error: 'unauthorized',
      message: 'Authentication required'
    });
  }
  next();
};

const config = require('../config');

/**
 * Middleware for internal service-to-service authentication.
 * Verifies the X-Internal-Secret header.
 */
const requireInternalSecret = (req, res, next) => {
  const secret = req.headers['x-internal-secret'];
  if (!secret || secret !== config.INTERNAL_API_SECRET) {
    return res.status(403).json({
      error: 'forbidden',
      message: 'Unauthorized internal access'
    });
  }
  next();
};

module.exports = { requireSession, requireInternalSecret };


