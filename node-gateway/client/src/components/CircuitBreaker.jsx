import React, { useState } from 'react';
import { ShieldAlert } from 'lucide-react';
import { postClient } from '../api/client';

export default function CircuitBreaker({ haltReasons, onResetSuccess }) {
  const [showConfirm, setShowConfirm] = useState(false);
  const [confirmText, setConfirmText] = useState('');
  const [isResetting, setIsResetting] = useState(false);
  const [error, setError] = useState(null);

  const handleReset = async () => {
    if (confirmText !== 'CONFIRM') {
      setError('You must type EXACTLY "CONFIRM"');
      return;
    }

    setIsResetting(true);
    setError(null);
    try {
      await postClient('/api/proxy/circuit-breaker/reset');
      setShowConfirm(false);
      setConfirmText('');
      if (onResetSuccess) onResetSuccess();
    } catch (err) {
      setError(err.message || 'Failed to reset circuit breaker');
    } finally {
      setIsResetting(false);
    }
  };

  return (
    <div className="bg-red-900/40 border border-red-700 rounded-lg p-4 mb-6 shadow-sm w-full">
      <div className="flex items-center space-x-2 text-red-400 mb-2">
        <ShieldAlert size={24} />
        <h2 className="text-xl font-bold">TRADING HALTED: CIRCUIT BREAKER TRIPPED</h2>
      </div>
      
      <ul className="list-disc pl-8 mb-4 text-red-200">
        {haltReasons && haltReasons.map((reason, idx) => (
          <li key={idx}>{reason}</li>
        ))}
      </ul>

      {!showConfirm ? (
        <button 
          onClick={() => setShowConfirm(true)}
          className="bg-red-700 hover:bg-red-600 text-white font-medium py-2 px-4 rounded transition"
        >
          Request Reset
        </button>
      ) : (
        <div className="bg-gray-900 p-4 rounded mt-4 border border-red-800">
          <p className="text-sm text-gray-300 mb-2">
            Warning: Resetting the circuit breaker resumes automated trading. 
            Type <strong>CONFIRM</strong> to proceed.
          </p>
          <div className="flex space-x-2">
            <input 
              type="text" 
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="CONFIRM"
              className="bg-gray-800 border border-gray-700 text-white px-3 py-2 rounded outline-none focus:border-red-500 uppercase"
            />
            <button 
              onClick={handleReset}
              disabled={isResetting || confirmText !== 'CONFIRM'}
              className="bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white font-medium py-2 px-4 rounded transition"
            >
              {isResetting ? 'Resetting...' : 'Confirm Reset'}
            </button>
            <button 
              onClick={() => { setShowConfirm(false); setConfirmText(''); setError(null); }}
              className="bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded transition"
            >
              Cancel
            </button>
          </div>
          {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
        </div>
      )}
    </div>
  );
}
