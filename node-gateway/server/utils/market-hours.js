/**
 * Checks if the current time in IST is within active market hours.
 * Market Hours: 09:15 - 15:30 IST, Monday to Friday.
 */
function isMarketOpen() {
  const options = { timeZone: 'Asia/Kolkata', hour12: false };
  const now = new Date();
  
  // Format returns "YYYY-MM-DD, HH:mm:ss"
  const formatter = new Intl.DateTimeFormat('en-US', {
    ...options,
    weekday: 'short',
    hour: 'numeric',
    minute: 'numeric',
    second: 'numeric'
  });
  
  const parts = formatter.formatToParts(now);
  const getPart = (type) => parts.find(p => p.type === type).value;
  
  const weekday = getPart('weekday');
  const hour = parseInt(getPart('hour'), 10);
  const minute = parseInt(getPart('minute'), 10);
  
  if (weekday === 'Sat' || weekday === 'Sun') {
    return false;
  }
  
  const timeInMinutes = hour * 60 + minute;
  const marketOpen = 9 * 60 + 15; // 09:15
  const marketClose = 15 * 60 + 30; // 15:30
  
  return timeInMinutes >= marketOpen && timeInMinutes < marketClose;
}

/**
 * Checks if the current time in IST is in the pre-market window.
 * Pre-Market: 09:00 - 09:15 IST, Monday to Friday.
 */
function isPreMarket() {
  const options = { timeZone: 'Asia/Kolkata', hour12: false };
  const now = new Date();
  
  const formatter = new Intl.DateTimeFormat('en-US', {
    ...options,
    weekday: 'short',
    hour: 'numeric',
    minute: 'numeric'
  });
  
  const parts = formatter.formatToParts(now);
  const getPart = (type) => parts.find(p => p.type === type).value;
  
  const weekday = getPart('weekday');
  const hour = parseInt(getPart('hour'), 10);
  const minute = parseInt(getPart('minute'), 10);
  
  if (weekday === 'Sat' || weekday === 'Sun') {
    return false;
  }
  
  const timeInMinutes = hour * 60 + minute;
  const preMarketOpen = 9 * 60; // 09:00
  const marketOpen = 9 * 60 + 15; // 09:15
  
  return timeInMinutes >= preMarketOpen && timeInMinutes < marketOpen;
}

module.exports = { isMarketOpen, isPreMarket };
