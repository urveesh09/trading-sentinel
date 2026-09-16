'use strict';

// Resolve the one configuration-dependent input to the otherwise pure session
// classifier. The Python engine is authoritative; a Node environment variable
// here would create a second, silently divergent eligibility list.
const config = require('../config');
const crypto = require('crypto');
const {
  isCashCasEligibilityResolutionWindow,
  isExecutionAllowed,
} = require('../utils/market-hours');

const ELIGIBILITY_SOURCE = 'python-engine/market_calendar.py::is_cas_eligible';
const SOURCE_VERSION_RE = /^[0-9a-f]{16}$/;
const SIGNATURE_RE = /^[0-9a-f]{64}$/;

function validSignature(body) {
  if (!SIGNATURE_RE.test(body.signature || '')) return false;
  const message = `${body.symbol}|${String(body.cas_eligible).toLowerCase()}|${body.source_version}`;
  const expected = crypto.createHmac('sha256', config.INTERNAL_API_SECRET).update(message).digest('hex');
  return crypto.timingSafeEqual(Buffer.from(body.signature, 'hex'), Buffer.from(expected, 'hex'));
}


async function resolveCasEligibility(symbol, observationAt = new Date()) {
  if (!isCashCasEligibilityResolutionWindow(observationAt)) {
    return { required: false, resolved: true, casEligible: false };
  }
  if (typeof symbol !== 'string' || !symbol.trim()) {
    return {
      required: true, resolved: false, casEligible: null,
      reason: 'CAS eligibility cannot be resolved without a symbol.',
    };
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.PYTHON_ENGINE_TIMEOUT_MS);
  const url = `${String(config.PYTHON_ENGINE_URL).replace(/\/$/, '')}` +
    `/market-session/cas-eligibility?symbol=${encodeURIComponent(symbol.trim())}`;
  try {
    const response = await fetch(url, {
      headers: { 'X-Internal-Secret': config.INTERNAL_API_SECRET },
      signal: controller.signal,
    });
    if (!response.ok) {
      return {
        required: true, resolved: false, casEligible: null,
        reason: `CAS eligibility service returned HTTP ${response.status}.`,
      };
    }
    const body = await response.json();
    const requestedSymbol = symbol.trim().toUpperCase();
    if (!body || typeof body.cas_eligible !== 'boolean' ||
        body.symbol !== requestedSymbol || body.source !== ELIGIBILITY_SOURCE ||
        typeof body.source_version !== 'string' ||
        !SOURCE_VERSION_RE.test(body.source_version) || !validSignature(body)) {
      return {
        required: true, resolved: false, casEligible: null,
        reason: 'CAS eligibility service returned an invalid payload.',
      };
    }
    return {
      required: true, resolved: true, casEligible: body.cas_eligible,
      source: body.source || null, sourceVersion: body.source_version || null,
    };
  } catch (_) {
    return {
      required: true, resolved: false, casEligible: null,
      reason: 'CAS eligibility service is unavailable; entry blocked.',
    };
  } finally {
    clearTimeout(timeout);
  }
}


async function entrySessionVerdict(symbol, observationAt = new Date()) {
  const eligibility = await resolveCasEligibility(symbol, observationAt);
  if (eligibility.required && !eligibility.resolved) {
    return {
      allowed: false,
      phase: 'CAS_ELIGIBILITY_UNAVAILABLE',
      reason: eligibility.reason,
      eligibility,
    };
  }
  const verdict = isExecutionAllowed({
    observation_at: observationAt,
    symbol,
    cas_eligible: eligibility.casEligible,
  });
  return { ...verdict, eligibility };
}


module.exports = { resolveCasEligibility, entrySessionVerdict };
