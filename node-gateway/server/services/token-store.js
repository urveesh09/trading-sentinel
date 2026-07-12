/**
 * IN-MEMORY TOKEN STORE
 * Absolute Constraint: node-gateway must never write access tokens to
 * disk, logs, or localStorage.
 *
 * [ROADMAP-2.1 2026-07-12] Constraint history: python-engine has
 * persisted the day's token to /data since 2026-07-09 (restart re-arm
 * fix), so the token already lives on the shared volume. This store
 * stays memory-only and write-free; on boot it may be RE-ARMED from
 * the engine over the authenticated internal channel
 * (services/token-restore.js), which adds no new disk exposure.
 */
let currentAccessToken = null;
let isTokenExpired = true;
let tokenGeneratedAt = null;

module.exports = {
  setToken: (token) => {
    currentAccessToken = token;
    isTokenExpired = false;
    tokenGeneratedAt = new Date().toISOString();
  },
  
  getToken: () => currentAccessToken,
  
  isValid: () => !isTokenExpired && currentAccessToken !== null,
  
  markExpired: () => {
    isTokenExpired = true;
  },
  
  clearToken: () => {
    currentAccessToken = null;
    isTokenExpired = true;
    tokenGeneratedAt = null;
  },

  getStatus: () => ({
    status: isTokenExpired ? 'expired' : (currentAccessToken ? 'active' : 'none'),
    generatedAt: tokenGeneratedAt
  })
};
