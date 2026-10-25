/**
 * [O25c] Kite through an encrypted tunnel: CONNECT through the registered VM, HTTPS inside it.
 *
 * The fake tunnel here answers CONNECT and pipes to a local plain-HTTP "Kite";
 * the test agent skips TLS (`_secure` returns the tunnel socket) so the bytes
 * can be read. The TLS step itself is checked against tls.connect.
 */
const http = require('http');
const net = require('net');
const tls = require('tls');
const axios = require('axios');

const {
  ConnectTunnelAgent, KITE_HTTPS_ROOT, kiteConnectThrough, kiteTransport, parseProxyUrl,
} = require('../../services/kite-tunnel');

class PlainAgent extends ConnectTunnelAgent {
  _secure(socket) { return socket; }
}

function listen(server) {
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server.address().port)));
}

function close(server) {
  return new Promise((resolve) => server.close(() => resolve()));
}

/** A tunnel like scripts/kite_tunnel.py: CONNECT api.kite.trade:443 with the password, piped to `kitePort`. */
function fakeTunnel(kitePort, { status = 200, expectAuth } = {}) {
  const seen = [];
  const server = net.createServer((client) => {
    let head = '';
    client.on('data', function onData(chunk) {
      head += chunk.toString('latin1');
      if (!head.includes('\r\n\r\n')) return;
      client.removeListener('data', onData);
      seen.push(head);
      const auth = /proxy-authorization: (.+)\r\n/i.exec(head);
      const answer = expectAuth && (!auth || auth[1] !== expectAuth) ? 407 : status;
      if (answer !== 200) {
        client.end(`HTTP/1.1 ${answer} No\r\nContent-Length: 0\r\n\r\n`);
        return;
      }
      const kite = net.connect(kitePort, '127.0.0.1', () => {
        client.write('HTTP/1.1 200 Connection established\r\n\r\n');
        client.pipe(kite).pipe(client);
      });
    });
  });
  return { server, seen };
}

function fakeKite() {
  const seen = [];
  const server = http.createServer((req, res) => {
    seen.push({ method: req.method, url: req.url, authorization: req.headers.authorization, host: req.headers.host });
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({ status: 'success', data: { user_id: 'AB1234' } }));
  });
  return { server, seen };
}

const BASIC = `Basic ${Buffer.from('kite:s3cret-0123456789abcdef').toString('base64')}`;

describe('KITE_PROXY_URL', () => {
  test('is parsed with its password kept out of what is shown', () => {
    const proxy = parseProxyUrl('http://kite:s3cret-0123456789abcdef@161.118.160.180:31528');
    expect(proxy).toMatchObject({ host: '161.118.160.180', port: 31528, authorization: BASIC });
    expect(proxy.display).toBe('161.118.160.180:31528 (user kite, password hidden)');
    expect(() => parseProxyUrl('https://kite:x@vm:31528')).toThrow(/http:\/\//);
    expect(() => parseProxyUrl('http://vm')).toThrow(/port/);
    expect(() => parseProxyUrl('not a url')).toThrow(/not a URL/);
  });

  test('unset leaves the route as it was; set, every call is HTTPS to Kite through the tunnel', () => {
    expect(kiteTransport({ KITE_BASE_URL: 'http://161.118.160.180:31527' })).toMatchObject({
      root: 'http://161.118.160.180:31527', httpsAgent: null, requestOptions: {}, encrypted: false });
    expect(kiteTransport({})).toMatchObject({ root: KITE_HTTPS_ROOT, encrypted: true, httpsAgent: null });
    const tunnel = kiteTransport({
      KITE_BASE_URL: 'http://161.118.160.180:31527',
      KITE_PROXY_URL: 'http://kite:s3cret-0123456789abcdef@161.118.160.180:31528',
    });
    expect(tunnel.root).toBe(KITE_HTTPS_ROOT);
    expect(tunnel.httpsAgent).toBeInstanceOf(ConnectTunnelAgent);
    expect(tunnel.requestOptions).toEqual({ httpsAgent: tunnel.httpsAgent, proxy: false });
    expect(tunnel.ignoredBase).toBe('http://161.118.160.180:31527');
    expect(tunnel.route).not.toContain('s3cret');
    expect(() => kiteTransport({ KITE_PROXY_URL: 'ftp://vm:1' })).toThrow();     // a broken route fails loudly
  });
});

describe('ConnectTunnelAgent', () => {
  let kite;
  let tunnel;
  let tunnelPort;

  beforeEach(async () => {
    kite = fakeKite();
    const kitePort = await listen(kite.server);
    tunnel = fakeTunnel(kitePort, { expectAuth: BASIC });
    tunnelPort = await listen(tunnel.server);
  });

  afterEach(async () => {
    await close(tunnel.server);
    await close(kite.server);
  });

  test('the direct LTP call goes through the tunnel with the password; the token rides inside it', async () => {
    const agent = new PlainAgent(parseProxyUrl(`http://kite:s3cret-0123456789abcdef@127.0.0.1:${tunnelPort}`));
    const response = await axios.get(`${KITE_HTTPS_ROOT}/quote/ltp?i=NSE:INFY`, {
      headers: { Authorization: 'token key:token' }, httpsAgent: agent, proxy: false, timeout: 5000,
    });
    expect(response.data.data.user_id).toBe('AB1234');
    expect(tunnel.seen[0]).toMatch(/^CONNECT api\.kite\.trade:443 HTTP\/1\.1\r\n/);
    expect(tunnel.seen[0]).toContain(`Proxy-Authorization: ${BASIC}`);
    expect(tunnel.seen[0]).not.toContain('token key:token');                 // never in the tunnel's head
    expect(kite.seen[0]).toMatchObject({ url: '/quote/ltp?i=NSE:INFY', authorization: 'token key:token' });
    agent.destroy();
  });

  test('the Kite SDK itself is built on the tunnel, and Telegram\'s axios is left alone', async () => {
    const { KiteConnect } = jest.requireActual('kiteconnect');
    const agent = new PlainAgent(parseProxyUrl(`http://kite:s3cret-0123456789abcdef@127.0.0.1:${tunnelPort}`));
    const sdk = kiteConnectThrough(KiteConnect, { api_key: 'key', root: KITE_HTTPS_ROOT }, agent);
    expect(axios.defaults.httpsAgent).toBeUndefined();
    expect(axios.defaults.proxy).toBeUndefined();
    sdk.setAccessToken('token');
    await expect(sdk.getProfile()).resolves.toEqual({ user_id: 'AB1234' });
    expect(tunnel.seen).toHaveLength(1);
    expect(kite.seen[0]).toMatchObject({ method: 'GET', url: '/user/profile', authorization: 'token key:token' });
    agent.destroy();
  });

  test('a wrong password is a refusal that names the tunnel and never the password', async () => {
    const agent = new PlainAgent(parseProxyUrl(`http://kite:wrong-0123456789abcdef@127.0.0.1:${tunnelPort}`));
    const failure = axios.get(`${KITE_HTTPS_ROOT}/user/profile`, { httpsAgent: agent, proxy: false, timeout: 5000 });
    await expect(failure).rejects.toThrow('the Kite tunnel refused CONNECT api.kite.trade:443: HTTP 407');
    await failure.catch((err) => expect(String(err.message)).not.toContain('wrong-'));
    expect(kite.seen).toHaveLength(0);
    agent.destroy();
  });

  test('a tunnel that never answers times out, and a closed port is unreachable', async () => {
    const held = [];
    const silent = net.createServer((socket) => held.push(socket));
    const silentPort = await listen(silent);
    const slow = new PlainAgent(parseProxyUrl(`http://kite:x@127.0.0.1:${silentPort}`), { connectTimeoutMs: 200 });
    await expect(axios.get(`${KITE_HTTPS_ROOT}/`, { httpsAgent: slow, proxy: false, timeout: 5000 }))
      .rejects.toThrow('did not open api.kite.trade:443 within 200 ms');
    slow.destroy();
    held.forEach((socket) => socket.destroy());
    await close(silent);
    const gone = new PlainAgent(parseProxyUrl(`http://kite:x@127.0.0.1:${silentPort}`));
    await expect(axios.get(`${KITE_HTTPS_ROOT}/`, { httpsAgent: gone, proxy: false, timeout: 5000 }))
      .rejects.toThrow('the Kite tunnel is unreachable');
    gone.destroy();
  });

  test('inside the tunnel it is TLS checked against api.kite.trade', () => {
    const spy = jest.spyOn(tls, 'connect').mockReturnValue('tls-socket');
    const agent = new ConnectTunnelAgent(parseProxyUrl('http://kite:x@127.0.0.1:1'));
    expect(agent._secure('raw-socket', {}, 'api.kite.trade')).toBe('tls-socket');
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({
      socket: 'raw-socket', servername: 'api.kite.trade', rejectUnauthorized: true }));
    spy.mockRestore();
    agent.destroy();
  });
});

describe('services/kite.js with KITE_PROXY_URL', () => {
  const saved = { ...process.env };

  afterEach(() => {
    process.env = { ...saved };
    jest.resetModules();
  });

  test('builds its SDK client on the tunnel and sends its LTP calls through it', () => {
    process.env.KITE_PROXY_URL = 'http://kite:s3cret-0123456789abcdef@161.118.160.180:31528';
    process.env.KITE_BASE_URL = 'http://161.118.160.180:31527';
    jest.isolateModules(() => {
      const constructed = [];
      jest.doMock('kiteconnect', () => ({
        KiteConnect: jest.fn(function KiteConnect(params) {
          // what kiteconnect's own axios.create() would copy from the defaults right now
          const sdkAxios = require('axios');
          constructed.push({ params, agent: sdkAxios.defaults.httpsAgent, proxy: sdkAxios.defaults.proxy });
        }),
      }));
      jest.doMock('../../middleware/logger', () => ({
        logger: { info: jest.fn(), error: jest.fn(), warn: jest.fn(), debug: jest.fn() },
      }));
      const { logger } = require('../../middleware/logger');
      const { ConnectTunnelAgent: Agent } = require('../../services/kite-tunnel');
      require('../../services/kite');
      const sdkAxios = require('axios');
      expect(constructed).toHaveLength(1);
      expect(constructed[0].params.root).toBe('https://api.kite.trade');
      expect(constructed[0].agent).toBeInstanceOf(Agent);
      expect(constructed[0].proxy).toBe(false);
      expect(sdkAxios.defaults.httpsAgent).toBeUndefined();                 // lent for the constructor only
      expect(logger.info).toHaveBeenCalledWith(expect.objectContaining({ event_type: 'kite_route', encrypted: true }),
        'Kite route');
      expect(JSON.stringify(logger.info.mock.calls)).not.toContain('s3cret');
      expect(logger.warn).toHaveBeenCalledWith(expect.objectContaining({ event_type: 'kite_base_url_ignored' }),
        expect.any(String));
    });
  });
});
