const { releaseIdentity } = require('../../release-identity');

describe('releaseIdentity', () => {
  const original = process.env;

  beforeEach(() => { process.env = { ...original }; });
  afterAll(() => { process.env = original; });

  test('marks an injected build SHA as declared', () => {
    process.env.SENTINEL_RELEASE_SHA = 'a'.repeat(40);
    process.env.SENTINEL_BUILD_UTC = '2026-09-09T12:00:00Z';
    process.env.SENTINEL_SERVICE_NAME = 'node-gateway';
    expect(releaseIdentity()).toEqual({
      service: 'node-gateway', revision: 'a'.repeat(40),
      build_utc: '2026-09-09T12:00:00Z', declared: true
    });
  });

  test('does not call a missing revision deployment proof', () => {
    delete process.env.SENTINEL_RELEASE_SHA;
    expect(releaseIdentity().declared).toBe(false);
    expect(releaseIdentity().revision).toBe('unknown');
  });
});
