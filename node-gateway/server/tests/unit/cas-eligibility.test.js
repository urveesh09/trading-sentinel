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
  const message = `${body.symbol}|${String(body.cas_eligible).toLowerCase()}|${body.source_version}`;
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
    await expect(resolveCasEligibility('RELIANCE', new Date())).resolves.toEqual({
      required: false, resolved: true, casEligible: false,
    });
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test('uses the authenticated Python projection in the affected interval', async () => {
    isCashCasEligibilityResolutionWindow.mockReturnValue(true);
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => signed({
        symbol: 'RELIANCE',
        cas_eligible: true,
        source: 'python-engine/market_calendar.py::is_cas_eligible',
        source_version: 'abcdef0123456789',
      }),
    });

    const result = await resolveCasEligibility('RELIANCE', new Date());
    expect(result).toEqual(expect.objectContaining({
      required: true, resolved: true, casEligible: true,
    }));
    expect(global.fetch).toHaveBeenCalledWith(
      'http://python-engine:8000/market-session/cas-eligibility?symbol=RELIANCE',
      expect.objectContaining({
        headers: { 'X-Internal-Secret': 'internal-test-secret' },
      })
    );
  });

  test.each([
    [signed({ symbol: 'OTHER', cas_eligible: true, source: 'python-engine/market_calendar.py::is_cas_eligible', source_version: 'abcdef0123456789' })],
    [signed({ symbol: 'RELIANCE', cas_eligible: true, source: 'untrusted', source_version: 'abcdef0123456789' })],
    [{ ...signed({ symbol: 'RELIANCE', cas_eligible: true, source: 'python-engine/market_calendar.py::is_cas_eligible', source_version: 'abcdef0123456789' }), signature: '0'.repeat(64) }],
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
});
