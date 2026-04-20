/**
 * NSE Trading Holidays for 2026.
 * UPDATE ANNUALLY from: https://www.nseindia.com/regulations/holiday-calendar
 * Format: 'YYYY-MM-DD' (IST calendar date)
 */
const NSE_HOLIDAYS = new Set([
  '2026-01-26', // Republic Day
  '2026-03-10', // Maha Shivaratri
  '2026-03-17', // Holi
  '2026-03-31', // Id-Ul-Fitr (Ramadan)
  '2026-04-03', // Good Friday
  '2026-04-14', // Dr. Ambedkar Jayanti
  '2026-05-01', // Maharashtra Day
  '2026-06-07', // Id-Ul-Adha (Bakri Id)
  '2026-07-07', // Muharram
  '2026-08-15', // Independence Day
  '2026-08-26', // Janmashtami
  '2026-09-05', // Milad-un-Nabi (Prophet's Birthday)
  '2026-10-02', // Mahatma Gandhi Jayanti
  '2026-10-20', // Dussehra
  '2026-11-09', // Diwali (Laxmi Puja)
  '2026-11-10', // Diwali (Balipratipada)
  '2026-11-27', // Guru Nanak Jayanti
  '2026-12-25', // Christmas
]);

/**
 * Returns the current date in IST as 'YYYY-MM-DD'.
 */
function getISTDate() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).format(new Date());
}

/**
 * Checks if the current time in IST is within active market hours.
 * Market Hours: 09:15 - 15:30 IST, Monday to Friday, excluding NSE holidays.
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

  // NSE holiday check
  if (NSE_HOLIDAYS.has(getISTDate())) {
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

module.exports = { isMarketOpen, isPreMarket, NSE_HOLIDAYS, getISTDate };
