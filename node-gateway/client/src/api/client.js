/**
 * Base fetcher for SWR.
 * INVIOLABLE RULE: `credentials: 'include'` must be present to send the httpOnly 
 * session cookie to Container A. The frontend never touches raw tokens.
 */
export const fetcher = async (url) => {
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json'
    },
    credentials: 'include' // Crucial for session auth
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const error = new Error(errorData.message || 'An error occurred while fetching the data.');
    error.info = errorData;
    error.status = response.status;
    throw error;
  }

  return response.json();
};

/**
 * Utility for POST requests (Executions, Circuit Breaker reset, etc.)
 */
export const postClient = async (url, body = {}) => {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json'
    },
    credentials: 'include',
    body: JSON.stringify(body)
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const error = new Error(data.message || 'Request failed');
    error.info = data;
    error.status = response.status;
    throw error;
  }

  return data;
};
