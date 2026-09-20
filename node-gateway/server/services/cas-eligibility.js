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

const ELIGIBILITY_SOURCE = 'python-engine/market_calendar.py::resolve_cas_eligibility';
const SOURCE_VERSION_RE = /^[0-9a-f]{16}$/;
const SIGNATURE_RE = /^[0-9a-f]{64}$/;
const VALID_STATES = new Set(['ELIGIBLE', 'NOT_ELIGIBLE', 'UNKNOWN']);
const VALID_REASONS = new Set([
  'listed',
  'not_listed',
  'empty_membership_list',
  'config_import_failed',
  'invalid_symbol',
  'stale_membership',
  'unknown',
]);

function validSignature(body, state, reason) {
  if (!SIGNATURE_RE.test(body.signature || '')) return false;
  const message =
    `${body.symbol}|${String(state).toLowerCase()}|${String(reason).toLowerCase()}|${body.source_version}`;
  const expected = crypto
    .createHmac('sha256', config.INTERNAL_API_SECRET)
    .update(message)
    .digest('hex');
  try {
    return crypto.timingSafeEqual(
      Buffer.from(body.signature, 'hex'),
      Buffer.from(expected, 'hex'),
    );
  } catch (_) {
    return false;
  }
}


async function resolveCasEligibility(symbol, observationAt = new Date()) {
  if (!isCashCasEligibilityResolutionWindow(observationAt)) {
    return {
      required: false, resolved: true,
      state: 'NOT_ELIGIBLE', reason: 'outside_resolution_window',
      casEligible: false,
    };
  }
  if (typeof symbol !== 'string' || !symbol.trim()) {
    return {
      required: true, resolved: false,
      state: 'UNKNOWN', reason: 'invalid_symbol',
      casEligible: null,
      detail: 'CAS eligibility cannot be resolved without a symbol.',
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
        required: true, resolved: false,
        state: 'UNKNOWN', reason: 'service_unavailable',
        casEligible: null,
        detail: `CAS eligibility service returned HTTP ${response.status}.`,
      };
    }
    const body = await response.json();
    const requestedSymbol = symbol.trim().toUpperCase();
    // Accept the new state/reason fields; reject if either is missing
    // or out of the bounded set. This prevents a future Python rollback
    // that drops the three-state fields from silently passing.
    if (
      !body || typeof body.cas_eligible !== 'boolean' ||
      body.symbol !== requestedSymbol || body.source !== ELIGIBILITY_SOURCE ||
      typeof body.source_version !== 'string' ||
      !SOURCE_VERSION_RE.test(body.source_version) ||
      !VALID_STATES.has(body.state) || !VALID_REASONS.has(body.reason) ||
      !validSignature(body, body.state, body.reason)
    ) {
      return {
        required: true, resolved: false,
        state: 'UNKNOWN', reason: 'invalid_payload',
        casEligible: null,
        detail: 'CAS eligibility service returned an invalid payload.',
      };
    }
    return {
      required: true, resolved: true,
      state: body.state, reason: body.reason,
      casEligible: body.state === 'ELIGIBLE',
      source: body.source || null,
      sourceVersion: body.source_version || null,
      coverage: body.coverage || null,
      asOfUtc: body.as_of_utc || null,
    };
  } catch (_) {
    return {
      required: true, resolved: false,
      state: 'UNKNOWN', reason: 'service_unavailable',
      casEligible: null,
      detail: 'CAS eligibility service is unavailable; entry blocked.',
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
      reason: eligibility.detail || eligibility.reason,
      eligibility,
    };
  }
  // A1: surface UNKNOWN distinctly from NOT_ELIGIBLE. The previous
  // boolean-only verdict collapsed both into "not CAS-eligible",
  // which silently turned the affected-window guard into a no-op
  // when the configuration was empty. UNKNOWN now blocks entry
  // explicitly.
  if (eligibility.required && eligibility.resolved && eligibility.state === 'UNKNOWN') {
    return {
      allowed: false,
      phase: 'CAS_ELIGIBILITY_UNKNOWN',
      reason: `CAS eligibility unknown: ${eligibility.reason}`,
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
