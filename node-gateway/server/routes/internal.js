const express = require('express');
const router = express.Router();
const { z } = require('zod');
const { requireInternalSecret } = require('../middleware/auth');
const { validate } = require('../middleware/validate');
const telegram = require('../services/telegram');

const notifySchema = z.object({
  message: z.string().min(1)
});

// POST /api/internal/notify
// Auth: X-Internal-Secret header
// Body: { message: string }
// Forwards message to TELEGRAM_CHAT_ID
router.post('/notify', requireInternalSecret, validate(notifySchema, 'body'), async (req, res, next) => {
  try {
    const { message } = req.body;
    await telegram.sendAlert(`🚨 [SYSTEM ALERT]\n${message}`);
    res.json({ success: true });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
