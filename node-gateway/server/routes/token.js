const express = require('express');
const router = express.Router();
const tokenStore = require('../services/token-store');
const { verifyInternalApi } = require('../middleware/security');
const config = require('../config');

// Container B requesting token
router.get('/', verifyInternalApi, (req, res) => {
  const tokenInfo = tokenStore.getStatus();
  
  if (!tokenStore.isValid()) {
    return res.status(401).json({ error: 'no_token', message: 'No active Zerodha token available' });
  }

  res.json({
    access_token: tokenStore.getToken(),
    generated_at: tokenInfo.generatedAt,
    api_key: config.ZERODHA_API_KEY
  });
});

// Container B reporting token expiration
router.post('/invalidate', verifyInternalApi, (req, res) => {
  tokenStore.markExpired();
  
  const telegram = require('../services/telegram');
  telegram.sendAlert('⚠️ Token invalidation requested by Quant Engine. Please re-authenticate.');
  
  res.json({ success: true, message: 'Token marked as expired' });
});

module.exports = router;
