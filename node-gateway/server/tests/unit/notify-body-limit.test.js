/**
 * [O9-M1 2026-10-09] The route-specific 64 KB parser must win over the general
 * 10 KB parser for /api/internal/notify only (the order used in app.js).
 */
const fs = require('fs');
const path = require('path');
const express = require('express');
const request = require('supertest');

function appLikeGateway() {
  const app = express();
  app.use('/api/internal/notify', express.json({ limit: '64kb' }));
  app.use(express.json({ limit: '10kb' }));
  app.post('/api/internal/notify', (req, res) => res.json({ n: req.body.message.length }));
  app.post('/api/other', (req, res) => res.json({ n: req.body.message.length }));
  app.use((err, req, res, next) => res.status(err.status || 500).json({ type: err.type })); // eslint-disable-line no-unused-vars
  return app;
}

test('app.js registers the notify parser before the general one', () => {
  const src = fs.readFileSync(path.join(__dirname, '../../app.js'), 'utf8');
  const notify = src.indexOf("app.use('/api/internal/notify', express.json({ limit: '64kb' }))");
  const general = src.indexOf("app.use(express.json({ limit: '10kb' }))");
  expect(notify).toBeGreaterThan(-1);
  expect(notify).toBeLessThan(general);
});

test('a 30 KB notify body is accepted; other routes keep the 10 KB limit', async () => {
  const app = appLikeGateway();
  const body = { message: 'x'.repeat(30000) };
  const ok = await request(app).post('/api/internal/notify').send(body);
  expect(ok.status).toBe(200);
  expect(ok.body.n).toBe(30000);
  const refused = await request(app).post('/api/other').send(body);
  expect(refused.status).toBe(413);
});
