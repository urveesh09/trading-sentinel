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

function signedHalt(body) {
  const message =
    `${body.channel}|${String(body.allowed).toLowerCase()}|` +
    `${String(body.global_halt).toLowerCase()}|` +
    `${String(body.per_channel).toLowerCase()}|${body.reason}|` +
    `${body.source_version}`;
  return {
    ...body,
    signature: crypto.createHmac('sha256', 'internal-test-secret').update(message).digest('hex'),
  };
}

const {
  isCashCasEligibilityResolutionWindow,
  isExecutionAllowed,
} = require('../../utils/market-hours');
const {
  resolveCasEligibility,
  resolveOwnerEntryHalt,
  entrySessionVerdict,
} = require('../../services/cas-eligibility');

describe('CAS eligibility resolver', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    isExecutionAllowed.mockReturnValue({
      allowed: true, phase: 'CONTINUOUS_TRADING', reason: null,
    });
  });

  afterEach(() => jest.useRealTimers());

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

  test('resolves the signed owner entry halt projection', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => signedHalt({
        channel: 'momentum',
        allowed: false,
        global_halt: true,
        per_channel: false,
        reason: 'global_owner_entry_halt',
        source: 'python-engine/owner_entry_halt.py::is_owner_entry_halted',
        source_version: 'abcdef0123456789',
      }),
    });
    const result = await resolveOwnerEntryHalt('momentum');
    expect(result).toEqual(expect.objectContaining({
      resolved: true,
      allowed: false,
      reason: 'global_owner_entry_halt',
    }));
    expect(global.fetch).toHaveBeenCalledWith(
      'http://python-engine:8000/market-session/owner-entry-halt?channel=momentum',
      expect.objectContaining({
        headers: { 'X-Internal-Secret': 'internal-test-secret' },
      }),
    );
  });

  test('fails closed on an invalid owner entry halt signature', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        ...signedHalt({
          channel: 'momentum',
          allowed: true,
          global_halt: false,
          per_channel: false,
          reason: 'allowed',
          source: 'python-engine/owner_entry_halt.py::is_owner_entry_halted',
          source_version: 'abcdef0123456789',
        }),
        signature: '0'.repeat(64),
      }),
    });
    const result = await resolveOwnerEntryHalt('momentum');
    expect(result).toEqual(expect.objectContaining({
      resolved: false,
      allowed: false,
      reason: 'invalid_payload',
    }));
  });

  test('entry session verdict can refresh the clock after resolver waits', async () => {
    isCashCasEligibilityResolutionWindow.mockReturnValue(false);
    isExecutionAllowed.mockReturnValue({
      allowed: true, phase: 'CONTINUOUS_TRADING', reason: null,
    });
    const result = await entrySessionVerdict(
      'TCS', new Date('2026-09-21T09:00:00.000Z'),
      { refreshClockAfterResolve: true },
    );
    expect(result.allowed).toBe(true);
    expect(isExecutionAllowed).toHaveBeenCalledWith(expect.objectContaining({
      observation_at: expect.any(Date),
    }));
  });

  const haltPayload = () => ({
    channel: 'momentum', allowed: true, global_halt: false, per_channel: false,
    reason: 'allowed', source: 'python-engine/owner_entry_halt.py::is_owner_entry_halted',
    source_version: 'abcdef0123456789',
  });

  test.each([
    { channel: 'fno' }, { source: 'untrusted' }, { source_version: 'bad' },
    { allowed: 'true' }, { allowed: true, global_halt: true },
    { allowed: true, per_channel: true },
    { allowed: true, reason: 'unknown_channel' },
    { allowed: false, reason: 'global_owner_entry_halt' },
    { allowed: false, reason: 'per_channel_owner_entry_halt' },
  ])('rejects signed but inconsistent owner projection %j', async (override) => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => signedHalt({ ...haltPayload(), ...override }) });
    expect(await resolveOwnerEntryHalt('momentum')).toMatchObject({
      resolved: false, allowed: false, reason: 'invalid_payload',
    });
  });

  test.each(['channel', 'allowed', 'global_halt', 'per_channel', 'reason', 'source_version'])(
    'rejects tampering with signed owner field %s', async (field) => {
      const body = signedHalt(haltPayload());
      body[field] = typeof body[field] === 'boolean' ? !body[field] : 'changed';
      global.fetch.mockResolvedValue({ ok: true, json: async () => body });
      expect(await resolveOwnerEntryHalt('momentum')).toMatchObject({ resolved: false, allowed: false });
    },
  );

  test.each(['http', 'network', 'json', 'abort'])('owner resolver fails closed on %s failure', async (failure) => {
    if (failure === 'http') global.fetch.mockResolvedValue({ ok: false, status: 503 });
    if (failure === 'network') global.fetch.mockRejectedValue(new Error('offline'));
    if (failure === 'json') global.fetch.mockResolvedValue({ ok: true, json: async () => { throw new Error('bad JSON'); } });
    if (failure === 'abort') {
      jest.useFakeTimers();
      global.fetch.mockImplementation((_url, { signal }) => new Promise((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(new Error('aborted')));
      }));
    }
    const pending = resolveOwnerEntryHalt('momentum');
    if (failure === 'abort') await jest.advanceTimersByTimeAsync(101);
    expect(await pending).toMatchObject({ resolved: false, allowed: false, reason: 'service_unavailable' });
  });

  test.each(['empty_membership_list', 'stale_membership', 'config_import_failed'])(
    'unknown CAS from %s blocks every affected phase using the real classifier', async (reason) => {
      global.fetch.mockResolvedValue({ ok: false, status: 503 });
      const realHours = jest.requireActual('../../utils/market-hours');
      global.fetch.mockClear();
      isCashCasEligibilityResolutionWindow.mockImplementation(realHours.isCashCasEligibilityResolutionWindow);
      isExecutionAllowed.mockImplementation(realHours.isExecutionAllowed);
      global.fetch.mockResolvedValue({ ok: true, json: async () => signed({
        symbol: 'TCS', state: 'UNKNOWN', reason, cas_eligible: false,
        source: 'python-engine/market_calendar.py::resolve_cas_eligibility',
        source_version: 'abcdef0123456789',
      }) });
      for (const time of ['09:45:00', '09:50:00', '09:55:00', '09:59:00']) {
        expect(await entrySessionVerdict('TCS', new Date(`2026-09-21T${time}Z`)))
          .toMatchObject({ allowed: false, phase: 'CAS_ELIGIBILITY_UNKNOWN' });
      }
      global.fetch.mockClear();
      expect(await entrySessionVerdict('TCS', new Date('2026-09-21T09:44:59Z')))
        .toMatchObject({ allowed: true, phase: 'CONTINUOUS_TRADING' });
      expect(global.fetch).not.toHaveBeenCalled();
    },
  );

  test('crossing into CAS resolves membership and uses the clock after that fetch', async () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-09-21T09:45:00Z'));
    global.fetch.mockResolvedValue({ ok: false, status: 503 });
      const realHours = jest.requireActual('../../utils/market-hours');
      global.fetch.mockClear();
    isCashCasEligibilityResolutionWindow.mockImplementation(realHours.isCashCasEligibilityResolutionWindow);
    isExecutionAllowed.mockImplementation(realHours.isExecutionAllowed);
    global.fetch.mockImplementation(async () => {
      jest.setSystemTime(new Date('2026-09-21T10:00:00Z'));
      return { ok: true, json: async () => signed({
        symbol: 'TCS', state: 'NOT_ELIGIBLE', reason: 'not_listed', cas_eligible: false,
        source: 'python-engine/market_calendar.py::resolve_cas_eligibility',
        source_version: 'abcdef0123456789',
      }) };
    });
    const verdict = await entrySessionVerdict('TCS', new Date('2026-09-21T09:44:59Z'), { refreshClockAfterResolve: true });
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(verdict.allowed).toBe(false);
    expect(isExecutionAllowed).toHaveBeenCalledWith(expect.objectContaining({
      observation_at: new Date('2026-09-21T10:00:00Z'),
    }));
  });
});
