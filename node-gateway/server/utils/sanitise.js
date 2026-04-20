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

module.exports = { sanitise };
