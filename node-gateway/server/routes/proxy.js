const express = require('express');
const router = express.Router();
const config = require('../config');
const { requireSession } = require('../middleware/auth');
const { logger } = require('../middleware/logger');

// Generic Proxy function
const proxyToEngine = async (req, res, path, method = 'GET') => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.PYTHON_ENGINE_TIMEOUT_MS);

  try {
    const fetchOptions = {
      method,
      headers: {
        'X-Internal-Secret': config.INTERNAL_API_SECRET,
        'Content-Type': 'application/json'
      },
      signal: controller.signal
    };

    if (method !== 'GET' && method !== 'HEAD' && req.body) {
      fetchOptions.body = JSON.stringify(req.body);
    }

    const response = await fetch(`${config.PYTHON_ENGINE_URL}${path}`, fetchOptions);
    clearTimeout(timeout);

    const data = await response.json();
    
    // Security: Strip internal headers from response if any exist
    res.removeHeader('x-internal-secret'); 
    
    res.status(response.status).json(data);
  } catch (err) {
    clearTimeout(timeout);
    logger.error({ event_type: 'proxy_error', path, err: err.message });
    res.status(502).json({ error: 'bad_gateway', message: 'Quant Engine is unreachable.' });
  }
};

router.use(requireSession);

// Map of endpoints to proxy
router.get('/signals', (req, res) => proxyToEngine(req, res, '/signals'));
router.get('/rejected', (req, res) => proxyToEngine(req, res, '/rejected'));
router.get('/positions', (req, res) => proxyToEngine(req, res, '/positions'));
router.get('/performance', (req, res) => proxyToEngine(req, res, '/performance'));
router.get('/health-b', (req, res) => proxyToEngine(req, res, '/health'));
router.get('/bankroll', (req, res) => proxyToEngine(req, res, '/bankroll'));
router.get('/circuit-breaker', (req, res) => proxyToEngine(req, res, '/circuit-breaker'));
router.post('/circuit-breaker/reset', (req, res) => proxyToEngine(req, res, '/circuit-breaker/reset', 'POST'));

module.exports = router;
