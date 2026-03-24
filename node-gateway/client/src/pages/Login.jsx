import React, { useState, useEffect } from 'react';
import { Clock } from 'lucide-react';

export default function Login({ healthData }) {
  const [istTime, setIstTime] = useState('');

  useEffect(() => {
    const timer = setInterval(() => {
      const timeString = new Date().toLocaleTimeString('en-US', {
        timeZone: 'Asia/Kolkata',
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      });
      setIstTime(`${timeString} IST`);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const isMarketOpen = healthData?.market_open || false;
  const lastLogin = healthData?.last_login_time 
    ? new Date(healthData.last_login_time).toLocaleString() 
    : 'Never';

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="max-w-md w-full bg-gray-900 border border-gray-800 rounded-xl shadow-2xl p-8 text-center">
        <h1 className="text-3xl font-bold text-white mb-2">Quant Gateway</h1>
        <p className="text-gray-400 mb-8">System Access & Execution Node</p>

        <div className="bg-gray-800 rounded-lg p-4 mb-8 flex justify-between items-center text-sm border border-gray-700">
          <div className="flex items-center space-x-2 text-gray-300">
            <Clock size={16} className="text-blue-400" />
            <span className="font-mono">{istTime}</span>
          </div>
          <div className={`px-2 py-1 rounded font-medium ${isMarketOpen ? 'bg-green-900/50 text-green-400' : 'bg-yellow-900/50 text-yellow-500'}`}>
            Market {isMarketOpen ? 'OPEN' : 'CLOSED'}
          </div>
        </div>

        <a 
          href="/api/auth/login"
          className="block w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 px-4 rounded transition-colors"
        >
          Connect Zerodha Account
        </a>

        <div className="mt-6 text-xs text-gray-500">
          Last login: {lastLogin}
        </div>
      </div>
    </div>
  );
}
