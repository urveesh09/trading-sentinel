'use strict';

// Only non-secret, deployment-supplied values are exposed.  A container does
// not need a .git checkout to identify the release it was built from.
const SHA_RE = /^[0-9a-f]{7,64}$/;

function bounded(value, fallback = 'unknown') {
  const text = String(value || '').trim();
  return (text || fallback).slice(0, 128);
}

function releaseIdentity(defaultService = 'node-gateway') {
  const revision = bounded(process.env.SENTINEL_RELEASE_SHA);
  return {
    service: bounded(process.env.SENTINEL_SERVICE_NAME, defaultService),
    revision,
    build_utc: bounded(process.env.SENTINEL_BUILD_UTC),
    declared: SHA_RE.test(revision)
  };
}

module.exports = { releaseIdentity };
