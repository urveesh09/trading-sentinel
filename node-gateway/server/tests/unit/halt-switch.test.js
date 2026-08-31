/**
 * [HALT 2026-08-05] Tests for the node half of the filesystem kill switch,
 * and for its enforcement at the kite.js broker chokepoint.
 *
 * The properties under test are the failure modes. A kill switch that works
 * when everything is fine is not a kill switch.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');

jest.mock('../../middleware/logger', () => ({
  logger: { error: jest.fn(), warn: jest.fn(), info: jest.fn() },
}));

let tmpDir;

/** Load a fresh halt-switch bound to a temp HALT_DIR. */
function loadHaltSwitch(dir) {
  jest.resetModules();
  process.env.HALT_DIR = dir;
  return require('../../services/halt-switch');
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'halt-test-'));
});

afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
  delete process.env.HALT_DIR;
});

describe('halt-switch: basic contract', () => {
  test('no sentinel means not halted', () => {
    const h = loadHaltSwitch(tmpDir);
    expect(h.haltState().halted).toBe(false);
  });

  test('a sentinel written by python is read as halted with attribution', () => {
    fs.writeFileSync(path.join(tmpDir, 'HALT'), JSON.stringify({
      tripped_at: '2026-08-05T04:00:00+00:00',
      by: 'circuit_breaker',
      reason: 'daily loss limit',
      scope: 'global',
    }));
    const h = loadHaltSwitch(tmpDir);
    const { halted, attribution } = h.haltState();
    expect(halted).toBe(true);
    expect(attribution.by).toBe('circuit_breaker');
    expect(attribution.reason).toBe('daily loss limit');
  });

  test('assertNotHalted throws TradingHaltedError', () => {
    fs.writeFileSync(path.join(tmpDir, 'HALT'), '{}');
    const h = loadHaltSwitch(tmpDir);
    expect(() => h.assertNotHalted()).toThrow(h.TradingHaltedError);
  });
});

describe('halt-switch: contents can never un-halt', () => {
  test('an empty touched file still halts', () => {
    fs.writeFileSync(path.join(tmpDir, 'HALT'), '');
    expect(loadHaltSwitch(tmpDir).haltState().halted).toBe(true);
  });

  test('corrupt JSON still halts', () => {
    fs.writeFileSync(path.join(tmpDir, 'HALT'), '{not json');
    expect(loadHaltSwitch(tmpDir).haltState().halted).toBe(true);
  });

  test('a payload claiming halted:false is ignored', () => {
    fs.writeFileSync(path.join(tmpDir, 'HALT'), JSON.stringify({ halted: false }));
    expect(loadHaltSwitch(tmpDir).haltState().halted).toBe(true);
  });

  test('a JSON array still halts and does not crash', () => {
    fs.writeFileSync(path.join(tmpDir, 'HALT'), '["nope"]');
    const { halted, attribution } = loadHaltSwitch(tmpDir).haltState();
    expect(halted).toBe(true);
    expect(attribution.by).toBe('manual_file');
  });

  test('a stat error that is not ENOENT fails CLOSED', () => {
    // This is the fail-open that fs.existsSync would have introduced: it
    // swallows EACCES/EIO into false.
    const h = loadHaltSwitch(tmpDir);
    const spy = jest.spyOn(fs, 'statSync').mockImplementation(() => {
      const err = new Error('EACCES: permission denied');
      err.code = 'EACCES';
      throw err;
    });
    const { halted, attribution } = h.haltState();
    expect(halted).toBe(true);
    expect(attribution.unreadable).toBe(true);
    spy.mockRestore();
  });
});

describe('halt-switch: scope', () => {
  test('a channel sentinel halts only that channel', () => {
    fs.writeFileSync(path.join(tmpDir, 'HALT.penny'), '{}');
    const h = loadHaltSwitch(tmpDir);
    expect(h.haltState('penny').halted).toBe(true);
    expect(h.haltState('momentum').halted).toBe(false);
    expect(h.haltState().halted).toBe(false);
  });

  test('the global sentinel wins over a clear channel', () => {
    fs.writeFileSync(path.join(tmpDir, 'HALT'), '{}');
    const h = loadHaltSwitch(tmpDir);
    expect(h.haltState('momentum').halted).toBe(true);
    expect(h.haltState('momentum').attribution.scope).toBe('global');
  });

  test('a channel name cannot escape HALT_DIR', () => {
    const h = loadHaltSwitch(tmpDir);
    const p = h.sentinelPath('../../etc/passwd');
    expect(path.dirname(path.resolve(p))).toBe(fs.realpathSync(tmpDir));
  });

  test('a channel that sanitises to empty fails closed rather than going global', () => {
    const h = loadHaltSwitch(tmpDir);
    const { halted, attribution } = h.haltState('///');
    expect(halted).toBe(true);
    expect(attribution.reason).toMatch(/invalid halt channel/);
  });
});

// ── Enforcement at the broker boundary ───────────────────────────────────

describe('kite.js enforcement', () => {
  let mockKite;
  let kiteService;
  let OrderExecutionError;

  function setup(dir) {
    jest.resetModules();
    process.env.HALT_DIR = dir;

    jest.doMock('kiteconnect', () => {
      const inst = {
        getLoginURL: jest.fn(),
        generateSession: jest.fn(),
        setAccessToken: jest.fn(),
        placeOrder: jest.fn().mockResolvedValue({ order_id: 'ORD-1' }),
        getOrderHistory: jest.fn(),
        placeGTT: jest.fn().mockResolvedValue({ trigger_id: 'GTT-1' }),
      };
      return { KiteConnect: jest.fn(() => inst), _mockInstance: inst };
    });
    jest.doMock('../../services/token-store', () => ({
      isValid: jest.fn().mockReturnValue(true),
      getToken: jest.fn().mockReturnValue('fake_token'),
      markExpired: jest.fn(),
    }));
    jest.doMock('../../services/telegram', () => ({ sendAlert: jest.fn() }));

    ({ _mockInstance: mockKite } = require('kiteconnect'));
    kiteService = require('../../services/kite');
    ({ OrderExecutionError } = require('../../utils/errors'));
  }

  test('an entry is blocked and never reaches the broker', async () => {
    fs.writeFileSync(path.join(tmpDir, 'HALT'), JSON.stringify({
      by: 'operator', reason: 'bad fills',
    }));
    setup(tmpDir);

    await expect(
      kiteService.placeOrder({ tradingsymbol: 'AAA' }, { intent: 'entry', channel: 'momentum' })
    ).rejects.toThrow(/bad fills/);
    expect(mockKite.placeOrder).not.toHaveBeenCalled();
  });

  test('an EXIT is never blocked — this is the point', async () => {
    fs.writeFileSync(path.join(tmpDir, 'HALT'), '{}');
    setup(tmpDir);

    const res = await kiteService.placeOrder(
      { tradingsymbol: 'AAA' }, { intent: 'exit', channel: 'momentum' }
    );
    expect(res).toEqual({ order_id: 'ORD-1' });
    expect(mockKite.placeOrder).toHaveBeenCalled();
  });

  test('a GTT exit leg is never blocked', async () => {
    fs.writeFileSync(path.join(tmpDir, 'HALT'), '{}');
    setup(tmpDir);

    const res = await kiteService.placeGTT({ tradingsymbol: 'AAA' }, { intent: 'exit' });
    expect(res).toEqual({ trigger_id: 'GTT-1' });
  });

  test('omitting intent throws rather than guessing', async () => {
    setup(tmpDir);
    await expect(kiteService.placeOrder({ tradingsymbol: 'AAA' }))
      .rejects.toThrow(/intent must be/);
    expect(mockKite.placeOrder).not.toHaveBeenCalled();
  });

  test('an unrecognised intent throws', async () => {
    setup(tmpDir);
    await expect(kiteService.placeOrder({ tradingsymbol: 'AAA' }, { intent: 'maybe' }))
      .rejects.toThrow(/intent must be/);
  });

  test('entries flow normally when no sentinel is present', async () => {
    setup(tmpDir);
    const res = await kiteService.placeOrder(
      { tradingsymbol: 'AAA' }, { intent: 'entry', channel: 'momentum' }
    );
    expect(res).toEqual({ order_id: 'ORD-1' });
  });

  test('a channel halt does not block a different channel', async () => {
    fs.writeFileSync(path.join(tmpDir, 'HALT.penny'), '{}');
    setup(tmpDir);
    const res = await kiteService.placeOrder(
      { tradingsymbol: 'AAA' }, { intent: 'entry', channel: 'momentum' }
    );
    expect(res).toEqual({ order_id: 'ORD-1' });
  });

  test('static-IP PermissionException atomically trips global halt but exits remain callable', async () => {
    setup(tmpDir);
    const denied = new Error('IP address is not allowed to place orders; configure static IP');
    denied.name = 'PermissionException';
    mockKite.placeOrder.mockRejectedValueOnce(denied);

    await expect(kiteService.placeOrder(
      { tradingsymbol: 'AAA' }, { intent: 'entry', channel: 'momentum' }
    )).rejects.toMatchObject({ authorizationDenied: true, retryable: false });

    const payload = JSON.parse(fs.readFileSync(path.join(tmpDir, 'HALT'), 'utf8'));
    expect(payload.by).toBe('kite_order_authorization');
    expect(payload.reason).toMatch(/static IP/i);

    mockKite.placeOrder.mockResolvedValueOnce({ order_id: 'EXIT-1' });
    await expect(kiteService.placeOrder(
      { tradingsymbol: 'AAA' }, { intent: 'exit', channel: 'momentum' }
    )).resolves.toEqual({ order_id: 'EXIT-1' });
  });
});
