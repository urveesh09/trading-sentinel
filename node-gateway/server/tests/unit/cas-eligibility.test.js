jest.mock('../../config', () => ({
  PYTHON_ENGINE_URL: 'http://python-engine:8000',
  PYTHON_ENGINE_TIMEOUT_MS: 100,
  INTERNAL_API_SECRET: 'internal-test-secret',
}));

jest.mock('../../utils/market-hours', () => ({
  isCashCasEligibilityResolutionWindow: jest.fn(),
  isExecutionAllowed: jest.fn(() => ({
    allowed: true, phase: 'CONTINUOUS_TRADING', reason: null,
  })),
}));

const crypto = require('crypto');
global.fetch = jest.fn();

function signed(body) {
  const message = `${body.symbol}|${String(body.state).toLowerCase()}|${String(body.reason).toLowerCase()}|${body.source_version}`;
  return { ...body, signature: crypto.createHmac('sha256', 'internal-test-secret').update(message).digest('hex') };
}

const {
  isCashCasEligibilityResolutionWindow,
  isExecutionAllowed,
} = require('../../utils/market-hours');
const {
  resolveCasEligibility,
  entrySessionVerdict,
} = require('../../services/cas-eligibility');

describe('CAS eligibility resolver', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('does not fetch outside the affected cash-CAS interval', async () => {
    isCashCasEligibilityResolutionWindow.mockReturnValue(false);
    await expect(resolveCasEligibility('RELIANCE', new Date())).resolves.toEqual(expect.objectContaining({
      required: false, resolved: true, state: 'NOT_ELIGIBLE',
    }));
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test('uses the authenticated Python projection in the affected interval', async () => {
    isCashCasEligibilityResolutionWindow.mockReturnValue(true);
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => signed({
        symbol: 'RELIANCE',
        cas_eligible: true,
        state: 'ELIGIBLE',
        reason: 'listed',
        source: 'python-engine/market_calendar.py::resolve_cas_eligibility',
        source_version: 'abcdef0123456789',
      }),
    });

    const result = await resolveCasEligibility('RELIANCE', new Date());
    expect(result).toEqual(expect.objectContaining({
      required: true, resolved: true, state: 'ELIGIBLE', casEligible: true,
    }));
    expect(global.fetch).toHaveBeenCalledWith(
      'http://python-engine:8000/market-session/cas-eligibility?symbol=RELIANCE',
      expect.objectContaining({
        headers: { 'X-Internal-Secret': 'internal-test-secret' },
      })
    );
  });

  test.each([
    [signed({ symbol: 'OTHER', cas_eligible: true, state: 'ELIGIBLE', reason: 'listed', source: 'python-engine/market_calendar.py::resolve_cas_eligibility', source_version: 'abcdef0123456789' })],
    [signed({ symbol: 'RELIANCE', cas_eligible: true, state: 'ELIGIBLE', reason: 'listed', source: 'untrusted', source_version: 'abcdef0123456789' })],
    [{ ...signed({ symbol: 'RELIANCE', cas_eligible: true, state: 'ELIGIBLE', reason: 'listed', source: 'python-engine/market_calendar.py::resolve_cas_eligibility', source_version: 'abcdef0123456789' }), signature: '0'.repeat(64) }],
    // A1: missing state field must fail closed.
    [{ symbol: 'RELIANCE', cas_eligible: true, reason: 'listed', source: 'python-engine/market_calendar.py::resolve_cas_eligibility', source_version: 'abcdef0123456789', signature: '0'.repeat(64) }],
  ])('fails closed on an unbound projection payload %#', async (payload) => {
    isCashCasEligibilityResolutionWindow.mockReturnValue(true);
    global.fetch.mockResolvedValue({ ok: true, json: async () => payload });
    const result = await resolveCasEligibility('RELIANCE', new Date());
    expect(result.resolved).toBe(false);
    expect(result.casEligible).toBeNull();
  });

  test('fails closed when the affected-interval resolver is unavailable', async () => {
    isCashCasEligibilityResolutionWindow.mockReturnValue(true);
    global.fetch.mockRejectedValue(new Error('engine unavailable'));

    const verdict = await entrySessionVerdict('RELIANCE', new Date());
    expect(verdict).toEqual(expect.objectContaining({
      allowed: false,
      phase: 'CAS_ELIGIBILITY_UNAVAILABLE',
    }));
    expect(isExecutionAllowed).not.toHaveBeenCalled();
  });

  // [WORKFLOW-A1 2026-09-20] Three-state coverage.
  test('UNKNOWN state blocks entry distinctly from NOT_ELIGIBLE', async () => {
    isCashCasEligibilityResolutionWindow.mockReturnValue(true);
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => signed({
        symbol: 'RELIANCE',
        cas_eligible: false,
        state: 'UNKNOWN',
        reason: 'empty_membership_list',
        source: 'python-engine/market_calendar.py::resolve_cas_eligibility',
        source_version: 'abcdef0123456789',
      }),
    });
    const verdict = await entrySessionVerdict('RELIANCE', new Date());
    expect(verdict.allowed).toBe(false);
    expect(verdict.phase).toBe('CAS_ELIGIBILITY_UNKNOWN');
    expect(isExecutionAllowed).not.toHaveBeenCalled();
  });

  test('NOT_ELIGIBLE state allows entry (continues to phase gate)', async () => {
    isCashCasEligibilityResolutionWindow.mockReturnValue(true);
    isExecutionAllowed.mockReturnValueOnce({
      allowed: true, phase: 'CONTINUOUS_TRADING', reason: null,
    });
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => signed({
        symbol: 'TCS',
        cas_eligible: false,
        state: 'NOT_ELIGIBLE',
        reason: 'not_listed',
        source: 'python-engine/market_calendar.py::resolve_cas_eligibility',
        source_version: 'abcdef0123456789',
      }),
    });
    const verdict = await entrySessionVerdict('TCS', new Date());
    expect(verdict.allowed).toBe(true);
    expect(isExecutionAllowed).toHaveBeenCalled();
  });

  test('rejects unknown state values in the projection payload', async () => {
    isCashCasEligibilityResolutionWindow.mockReturnValue(true);
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => signed({
        symbol: 'RELIANCE',
        cas_eligible: false,
        state: 'MAYBE',
        reason: 'listed',
        source: 'python-engine/market_calendar.py::resolve_cas_eligibility',
        source_version: 'abcdef0123456789',
      }),
    });
    const result = await resolveCasEligibility('RELIANCE', new Date());
    expect(result.resolved).toBe(false);
    expect(result.state).toBe('UNKNOWN');
    expect(result.reason).toBe('invalid_payload');
  });

  test('rejects unknown reason values in the projection payload', async () => {
    isCashCasEligibilityResolutionWindow.mockReturnValue(true);
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => signed({
        symbol: 'RELIANCE',
        cas_eligible: false,
        state: 'NOT_ELIGIBLE',
        reason: 'unspecified',
        source: 'python-engine/market_calendar.py::resolve_cas_eligibility',
        source_version: 'abcdef0123456789',
      }),
    });
    const result = await resolveCasEligibility('RELIANCE', new Date());
    expect(result.resolved).toBe(false);
    expect(result.reason).toBe('invalid_payload');
  });
});
