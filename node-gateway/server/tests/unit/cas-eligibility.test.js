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

global.fetch = jest.fn();

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
      json: async () => ({
        cas_eligible: true,
        source: 'python-engine/market_calendar.py::is_cas_eligible',
        source_version: 'abc123',
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
