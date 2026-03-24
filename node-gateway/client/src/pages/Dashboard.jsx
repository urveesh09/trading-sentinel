import React, { useState } from 'react';
import StatusBar from '../components/StatusBar';
import SignalCard from '../components/SignalCard';
import PositionRow from '../components/PositionRow';
import CircuitBreaker from '../components/CircuitBreaker';
import { useSignals } from '../hooks/useSignals';
import { usePositions } from '../hooks/usePositions';
import { usePerformance } from '../hooks/usePerformance';

export default function Dashboard({ healthData, navigateToPositions }) {
  const { signals, mutate: refreshSignals } = useSignals();
  const { positions } = usePositions();
  const { performance } = usePerformance();

  // Extract circuit breaker status from health or positions endpoint proxy
  const cbHalted = healthData?.circuit_breaker_halted || false;
  const cbReasons = healthData?.circuit_breaker_reasons || [];
  const isMarketOpen = healthData?.market_open || false;

  // Render open positions or max 5 for the dashboard snippet
  const activePositions = Array.isArray(positions) 
    ? positions.filter(p => p.status === 'OPEN').slice(0, 5) 
    : [];

  return (
    <div className="min-h-screen flex flex-col bg-gray-950 text-gray-200">
      <StatusBar cbHalted={cbHalted} />

      <main className="flex-1 p-4 overflow-y-auto">
        <div className="max-w-7xl mx-auto">
          
          {cbHalted && (
            <CircuitBreaker haltReasons={cbReasons} onResetSuccess={() => window.location.reload()} />
          )}

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left Column: Signals */}
            <div className="lg:col-span-1 space-y-4">
              <h2 className="text-xl font-bold text-white border-b border-gray-800 pb-2">Active Signals</h2>
              {(!signals || signals.length === 0) ? (
                <div className="text-gray-500 text-sm italic p-4 bg-gray-900 rounded border border-gray-800">
                  No pending signals.
                </div>
              ) : (
                signals.map(sig => (
                  <SignalCard 
                    key={sig.signal_id} 
                    signal={sig} 
                    isMarketOpen={isMarketOpen}
                    cbHalted={cbHalted}
                    onActionComplete={refreshSignals}
                  />
                ))
              )}
            </div>

            {/* Right Column: Positions */}
            <div className="lg:col-span-2">
              <div className="flex justify-between items-end border-b border-gray-800 pb-2 mb-4">
                <h2 className="text-xl font-bold text-white">Open Positions</h2>
                <button onClick={navigateToPositions} className="text-sm text-blue-400 hover:text-blue-300">
                  View All →
                </button>
              </div>
              
              <div className="bg-gray-900 rounded border border-gray-800 overflow-x-auto">
                <table className="w-full text-left text-sm whitespace-nowrap">
                  <thead className="bg-gray-800 text-gray-400">
                    <tr>
                      <th className="p-3 font-medium">Ticker</th>
                      <th className="p-3 font-medium">Entry</th>
                      <th className="p-3 font-medium">Stop</th>
                      <th className="p-3 font-medium">T1</th>
                      <th className="p-3 font-medium">T2</th>
                      <th className="p-3 font-medium">Unrealised P&L</th>
                      <th className="p-3 font-medium">R-Mult</th>
                      <th className="p-3 font-medium">Days</th>
                      <th className="p-3 font-medium">Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activePositions.length === 0 ? (
                      <tr>
                        <td colSpan="9" className="p-6 text-center text-gray-500 italic">No open positions.</td>
                      </tr>
                    ) : (
                      activePositions.map(pos => <PositionRow key={pos.order_id} position={pos} />)
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Bottom Performance Bar */}
      <footer className="bg-gray-900 border-t border-gray-800 p-4">
        <div className="max-w-7xl mx-auto flex justify-between items-center text-sm font-mono">
          <div className="text-gray-400">
            Bankroll: <span className="text-white">₹{performance?.current_bankroll || '---'}</span>
          </div>
          <div className="text-gray-400">
            Total P&L: <span className={performance?.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
              {performance?.total_pnl >= 0 ? '+' : ''}₹{performance?.total_pnl || '0.00'}
            </span>
          </div>
          <div className="text-gray-400">
            Win Rate: <span className="text-white">{performance?.win_rate || '---'}%</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
