/**
 * IN-MEMORY TOKEN STORE
 * Absolute Constraint: Access tokens must never be written to disk, logs, or localStorage.
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
