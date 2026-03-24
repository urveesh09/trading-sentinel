/**
 * Middleware to protect routes that require an authenticated active session.
 */
const requireSession = (req, res, next) => {
  if (req.session && req.session.authenticated) {
    return next();
  }
  
  // Return a generic safe message. 
  return res.status(401).json({
    error: 'unauthorized',
    message: 'Active session required. Please connect Zerodha.'
  });
};

module.exports = { requireSession };
