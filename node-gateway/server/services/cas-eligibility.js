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
const OWNER_ENTRY_HALT_SOURCE = 'python-engine/owner_entry_halt.py::is_owner_entry_halted';
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
const VALID_HALT_REASONS = new Set([
  'allowed',
  'global_owner_entry_halt',
  'per_channel_owner_entry_halt',
  'unknown_channel',
  'config_import_failed',
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

function validOwnerEntryHaltSignature(body) {
  if (!SIGNATURE_RE.test(body.signature || '')) return false;
  const message =
    `${body.channel}|${String(body.allowed).toLowerCase()}|` +
    `${String(body.global_halt).toLowerCase()}|` +
    `${String(body.per_channel).toLowerCase()}|${body.reason}|` +
    `${body.source_version}`;
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
      body.cas_eligible !== (body.state === 'ELIGIBLE') ||
      (body.state === 'ELIGIBLE' && body.reason !== 'listed') ||
      (body.state === 'NOT_ELIGIBLE' && body.reason !== 'not_listed') ||
      (body.state === 'UNKNOWN' && ['listed', 'not_listed'].includes(body.reason)) ||
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


async function resolveOwnerEntryHalt(channel = 'momentum') {
  if (typeof channel !== 'string' || !channel.trim()) {
    return {
      resolved: false,
      allowed: false,
      reason: 'invalid_channel',
      detail: 'Owner entry halt cannot be resolved without a channel.',
    };
  }
  const requestedChannel = channel.trim().toLowerCase();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.PYTHON_ENGINE_TIMEOUT_MS);
  const url = `${String(config.PYTHON_ENGINE_URL).replace(/\/$/, '')}` +
    `/market-session/owner-entry-halt?channel=${encodeURIComponent(requestedChannel)}`;
  try {
    const response = await fetch(url, {
      headers: { 'X-Internal-Secret': config.INTERNAL_API_SECRET },
      signal: controller.signal,
    });
    if (!response.ok) {
      return {
        resolved: false,
        allowed: false,
        reason: 'service_unavailable',
        detail: `Owner entry halt service returned HTTP ${response.status}.`,
      };
    }
    const body = await response.json();
    if (
      !body || body.channel !== requestedChannel ||
      typeof body.allowed !== 'boolean' ||
      typeof body.global_halt !== 'boolean' ||
      typeof body.per_channel !== 'boolean' ||
      !VALID_HALT_REASONS.has(body.reason) ||
      body.allowed !== (body.reason === 'allowed') ||
      (body.allowed && (body.global_halt || body.per_channel)) ||
      (body.global_halt && body.reason !== 'global_owner_entry_halt') ||
      (body.reason === 'global_owner_entry_halt' && !body.global_halt) ||
      (body.reason === 'per_channel_owner_entry_halt' && !body.per_channel) ||
      body.source !== OWNER_ENTRY_HALT_SOURCE ||
      typeof body.source_version !== 'string' ||
      !SOURCE_VERSION_RE.test(body.source_version) ||
      !validOwnerEntryHaltSignature(body)
    ) {
      return {
        resolved: false,
        allowed: false,
        reason: 'invalid_payload',
        detail: 'Owner entry halt service returned an invalid payload.',
      };
    }
    return {
      resolved: true,
      allowed: body.allowed,
      globalHalt: body.global_halt,
      perChannel: body.per_channel,
      reason: body.reason,
      source: body.source,
      sourceVersion: body.source_version,
    };
  } catch (_) {
    return {
      resolved: false,
      allowed: false,
      reason: 'service_unavailable',
      detail: 'Owner entry halt service is unavailable; entry blocked.',
    };
  } finally {
    clearTimeout(timeout);
  }
}


async function entrySessionVerdict(
  symbol,
  observationAt = new Date(),
  { refreshClockAfterResolve = false } = {},
) {
  let eligibility = await resolveCasEligibility(symbol, observationAt);
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
  let phaseObservationAt = observationAt;
  // The final dispatch check runs after broker margin preflight. If the
  // resolver started just before 15:15, re-evaluate the clock after its
  // network wait and resolve CAS membership if the window was crossed.
  if (refreshClockAfterResolve) {
    phaseObservationAt = new Date();
    if (
      isCashCasEligibilityResolutionWindow(phaseObservationAt) &&
      !eligibility.required
    ) {
      const refreshed = await resolveCasEligibility(symbol, phaseObservationAt);
      if (refreshed.required && !refreshed.resolved) {
        return {
          allowed: false,
          phase: 'CAS_ELIGIBILITY_UNAVAILABLE',
          reason: refreshed.detail || refreshed.reason,
          eligibility: refreshed,
        };
      }
      if (refreshed.required && refreshed.state === 'UNKNOWN') {
        return {
          allowed: false,
          phase: 'CAS_ELIGIBILITY_UNKNOWN',
          reason: `CAS eligibility unknown: ${refreshed.reason}`,
          eligibility: refreshed,
        };
      }
      eligibility = refreshed;
      phaseObservationAt = new Date();
    }
  }
  const verdict = isExecutionAllowed({
    observation_at: phaseObservationAt,
    symbol,
    cas_eligible: eligibility.casEligible,
  });
  return { ...verdict, eligibility };
}


module.exports = {
  resolveCasEligibility,
  resolveOwnerEntryHalt,
  entrySessionVerdict,
};
