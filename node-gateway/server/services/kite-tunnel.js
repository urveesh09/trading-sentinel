'use strict';

/**
 * [O25c 2026-10-25] Kite through an encrypted tunnel.
 *
 * KITE_BASE_URL=http://161.118.160.180:31527 (the plain-HTTP relay on the
 * Oracle VM) sends every Kite request, with its Authorization header (the API
 * key and the day's access token), across the internet in clear text.
 * KITE_PROXY_URL instead opens an HTTP CONNECT tunnel through that VM
 * (scripts/kite_tunnel.py) and speaks HTTPS to api.kite.trade inside it. The
 * token is encrypted all the way to Kite, and orders still leave from the VM's
 * registered static IP.
 *
 *   KITE_PROXY_URL=http://kite:<password>@161.118.160.180:31528
 *
 * Unset, nothing changes. Only Kite's REST calls use it, never Telegram.
 */

const http = require('http');
const https = require('https');
const path = require('path');
const tls = require('tls');

const KITE_HTTPS_ROOT = 'https://api.kite.trade';
const CONNECT_TIMEOUT_MS = 10000;

function parseProxyUrl(raw) {
  let url;
  try {
    url = new URL(String(raw).trim());
  } catch (_) {
    throw new Error('KITE_PROXY_URL is not a URL');
  }
  if (url.protocol !== 'http:') {
    throw new Error('KITE_PROXY_URL must start with http:// (TLS runs inside the tunnel)');
  }
  if (!url.hostname || !url.port) {
    throw new Error('KITE_PROXY_URL needs a host and a port');
  }
  const user = decodeURIComponent(url.username || '');
  const password = decodeURIComponent(url.password || '');
  return {
    host: url.hostname.replace(/^\[|\]$/g, ''),
    port: Number(url.port),
    authorization: user || password
      ? `Basic ${Buffer.from(`${user}:${password}`).toString('base64')}`
      : null,
    display: `${url.hostname}:${url.port}${user ? ` (user ${user}, password hidden)` : ''}`,
  };
}

/** An https.Agent whose sockets are TLS to the target inside a CONNECT tunnel. */
class ConnectTunnelAgent extends https.Agent {
  constructor(proxy, options = {}) {
    super({ keepAlive: true, timeout: 30000, ...options });
    this.proxy = proxy;
    this.connectTimeoutMs = options.connectTimeoutMs || CONNECT_TIMEOUT_MS;
  }

  createConnection(options, callback) {
    const host = options.host || options.hostname;
    const port = Number(options.port) || 443;
    const target = `${host}:${port}`;
    let settled = false;
    const done = (err, socket) => {
      if (settled) return;
      settled = true;
      callback(err, socket);
    };
    const headers = { Host: target };
    if (this.proxy.authorization) headers['Proxy-Authorization'] = this.proxy.authorization;
    const request = http.request({
      host: this.proxy.host,
      port: this.proxy.port,
      method: 'CONNECT',
      path: target,
      headers,
      agent: false,
    });
    request.setTimeout(this.connectTimeoutMs, () => {
      request.destroy(new Error(`the Kite tunnel did not open ${target} within ${this.connectTimeoutMs} ms`));
    });
    request.once('connect', (response, socket, head) => {
      request.setTimeout(0);
      if (response.statusCode !== 200) {
        socket.destroy();
        done(new Error(`the Kite tunnel refused CONNECT ${target}: HTTP ${response.statusCode}`));
        return;
      }
      if (head && head.length) socket.unshift(head);
      try {
        done(null, this._secure(socket, options, host));
      } catch (err) {
        socket.destroy();
        done(err);
      }
    });
    request.once('error', (err) => done(String(err.message).startsWith('the Kite tunnel')
      ? err : new Error(`the Kite tunnel is unreachable: ${err.message}`)));
    request.end();
  }

  // TLS to the target over the tunnel, its certificate checked against the target's name.
  _secure(socket, options, host) {
    return tls.connect({
      socket,
      servername: options.servername || host,
      rejectUnauthorized: options.rejectUnauthorized !== false,
      ca: options.ca,
    });
  }
}

/**
 * The route Kite calls take: { root, httpsAgent, requestOptions, route, encrypted, ignoredBase }.
 * With KITE_PROXY_URL the root is always https://api.kite.trade (KITE_BASE_URL, the relay, is ignored).
 */
function kiteTransport(env = process.env) {
  const proxyRaw = String(env.KITE_PROXY_URL || '').trim();
  const base = String(env.KITE_BASE_URL || '').trim();
  if (!proxyRaw) {
    const root = base || KITE_HTTPS_ROOT;
    return { root, httpsAgent: null, requestOptions: {}, route: root, encrypted: root.startsWith('https://'),
      ignoredBase: null };
  }
  const proxy = parseProxyUrl(proxyRaw);
  const httpsAgent = new ConnectTunnelAgent(proxy);
  return {
    root: KITE_HTTPS_ROOT,
    httpsAgent,
    requestOptions: { httpsAgent, proxy: false },
    route: `${KITE_HTTPS_ROOT} through the tunnel ${proxy.display}`,
    encrypted: true,
    ignoredBase: base && base.replace(/\/+$/, '') !== KITE_HTTPS_ROOT ? base : null,
  };
}

/**
 * A KiteConnect whose requests use the tunnel. kiteconnect 3.x builds its
 * axios instance inside the constructor from axios.defaults and takes no
 * agent option, so the defaults of the axios it loads lend it the agent for
 * that one synchronous call and are put back at once.
 */
function kiteConnectThrough(KiteConnect, params, httpsAgent) {
  if (!httpsAgent) return new KiteConnect(params);
  const sdkAxios = require(require.resolve('axios', { paths: [path.dirname(require.resolve('kiteconnect'))] }));
  const saved = { httpsAgent: sdkAxios.defaults.httpsAgent, proxy: sdkAxios.defaults.proxy };
  sdkAxios.defaults.httpsAgent = httpsAgent;
  sdkAxios.defaults.proxy = false;
  try {
    return new KiteConnect(params);
  } finally {
    sdkAxios.defaults.httpsAgent = saved.httpsAgent;
    sdkAxios.defaults.proxy = saved.proxy;
  }
}

module.exports = {
  KITE_HTTPS_ROOT,
  ConnectTunnelAgent,
  parseProxyUrl,
  kiteTransport,
  kiteConnectThrough,
};
