const SENSITIVE_KEYS = new Set([
  'token', 'secret', 'password', 'access_token', 
  'api_key', 'api_secret', 'session', 'authorization',
  'cookie', 'telegram_token'
]);

/**
 * Recursively sanitizes objects by replacing sensitive string values.
 */
function sanitise(obj) {
  if (obj === null || typeof obj !== 'object') {
    return obj;
  }

  if (Array.isArray(obj)) {
    return obj.map(item => sanitise(item));
  }

  const sanitisedObj = {};
  for (const [key, value] of Object.entries(obj)) {
    const isSensitiveKey = [...SENSITIVE_KEYS].some(k => key.toLowerCase().includes(k));
    
    if (isSensitiveKey && typeof value === 'string') {
      sanitisedObj[key] = '[REDACTED]';
    } else if (typeof value === 'object') {
      sanitisedObj[key] = sanitise(value);
    } else {
      sanitisedObj[key] = value;
    }
  }
  
  return sanitisedObj;
}

/**
 * [MED-011 2026-07-12] Redacts sensitive query-string values in a URL.
 * The Zerodha OAuth callback arrives as
 *   /api/auth/callback?request_token=XXX&status=success
 * and pino-http logs req.url verbatim -- without this, a usable Kite
 * credential lands in the log stream on every daily login.
 */
function sanitiseUrl(url) {
  if (typeof url !== 'string') return url;
  const qIdx = url.indexOf('?');
  if (qIdx === -1) return url;

  const path = url.slice(0, qIdx);
  const query = url.slice(qIdx + 1).split('&').map((pair) => {
    const eq = pair.indexOf('=');
    if (eq === -1) return pair;
    const name = pair.slice(0, eq);
    const isSensitive = [...SENSITIVE_KEYS].some(k => name.toLowerCase().includes(k));
    return isSensitive ? `${name}=[REDACTED]` : pair;
  }).join('&');

  return `${path}?${query}`;
}

module.exports = { sanitise, sanitiseUrl };
