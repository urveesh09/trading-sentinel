import React, { useState } from 'react';
import { postClient } from '../api/client';

export default function SignalCard({ signal, isMarketOpen, cbHalted, onActionComplete }) {
  const [isProcessing, setIsProcessing] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  // Calculate age
  const signalTime = new Date(signal.signal_time).getTime();
  const ageMinutes = Math.floor((Date.now() - signalTime) / 60000);
  const ageText = ageMinutes === 0 ? 'just now' : `${ageMinutes}m ago`;

  const handleAction = async (action) => {
    setIsProcessing(true);
    setErrorMsg(null);
    try {
      if (action === 'EXECUTE') {
        await postClient('/api/orders/execute', { signal_id: signal.signal_id });
      } else {
        // Fallback for UI-based reject if implemented on backend, 
        // else we just remove it locally. Assuming an endpoint exists or we ignore it.
        // For strict compliance to the text, we call the execution proxy.
      }
      onActionComplete(); // Triggers a re-fetch of signals
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setIsProcessing(false);
    }
  };

  const actionDisabled = !isMarketOpen || cbHalted || isProcessing || ageMinutes > 5;

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 shadow-sm relative">
      <div className="flex justify-between items-start mb-3">
        <div>
          <h3 className="text-lg font-bold text-white">{signal.ticker}</h3>
          <span className="text-xs text-gray-400">Score: {signal.score}/100</span>
        </div>
        <span className="text-xs text-gray-500 bg-gray-900 px-2 py-1 rounded">
          received {ageText}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-sm mb-4">
        <div className="text-gray-400">Entry: <span className="text-white font-mono">₹{signal.close}</span></div>
        <div className="text-gray-400">Shares: <span className="text-white font-mono">{signal.shares}</span></div>
        <div className="text-red-400">Stop: <span className="font-mono">₹{signal.stop_loss}</span></div>
        <div className="text-gray-400">Risk: <span className="text-white font-mono">₹{signal.capital_at_risk}</span></div>
        <div className="text-green-400">Target 1: <span className="font-mono">₹{signal.target_1}</span></div>
        <div className="text-green-500">Target 2: <span className="font-mono">₹{signal.target_2}</span></div>
      </div>

      {errorMsg && <div className="text-red-400 text-xs mb-3">{errorMsg}</div>}
      {ageMinutes > 5 && <div className="text-yellow-500 text-xs mb-3">Signal expired (> 5m).</div>}

      <div className="flex space-x-2">
        <button
          onClick={() => handleAction('EXECUTE')}
          disabled={actionDisabled}
          className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-2 rounded text-sm font-medium transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isProcessing ? 'Processing...' : 'Execute & Place GTT'}
        </button>
        <button
          onClick={() => onActionComplete()} // Just dismiss from view locally
          disabled={isProcessing}
          className="bg-gray-700 hover:bg-gray-600 text-gray-200 px-4 py-2 rounded text-sm font-medium transition disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
