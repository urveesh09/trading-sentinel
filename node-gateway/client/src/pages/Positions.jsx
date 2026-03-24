import React, { useState } from 'react';
import PositionRow from '../components/PositionRow';
import { usePositions } from '../hooks/usePositions';
import StatusBar from '../components/StatusBar';

export default function Positions({ navigateToDashboard }) {
  const { positions, isLoading } = usePositions();
  const [sortField, setSortField] = useState('days_held');
  const [sortAsc, setSortAsc] = useState(false);

  const handleSort = (field) => {
    if (sortField === field) setSortAsc(!sortAsc);
    else {
      setSortField(field);
      setSortAsc(false);
    }
  };

  const sortedPositions = Array.isArray(positions) ? [...positions].sort((a, b) => {
    let valA = a[sortField];
    let valB = b[sortField];
    if (typeof valA === 'string') valA = valA.toLowerCase();
    if (typeof valB === 'string') valB = valB.toLowerCase();
    
    if (valA < valB) return sortAsc ? -1 : 1;
    if (valA > valB) return sortAsc ? 1 : -1;
    return 0;
  }) : [];

  return (
    <div className="min-h-screen flex flex-col bg-gray-950 text-gray-200">
      <StatusBar />
      <div className="p-4 max-w-7xl mx-auto w-full">
        <div className="flex items-center space-x-4 mb-6 border-b border-gray-800 pb-4">
          <button onClick={navigateToDashboard} className="text-gray-400 hover:text-white transition">
            ← Back to Dashboard
          </button>
          <h1 className="text-2xl font-bold text-white">All Positions Tracker</h1>
        </div>

        {isLoading ? (
          <div className="text-center p-10 text-gray-500 animate-pulse">Loading positions...</div>
        ) : (
          <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-x-auto shadow-lg">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead className="bg-gray-800 text-gray-400 select-none">
                <tr>
                  {['ticker', 'entry_price', 'current_stop', 'target_1', 'target_2', 'unrealised_pnl', 'r_multiple', 'days_held', 'source'].map(col => (
                    <th key={col} className="p-3 font-medium cursor-pointer hover:text-white transition" onClick={() => handleSort(col)}>
                      {col.replace('_', ' ').toUpperCase()} {sortField === col ? (sortAsc ? '↑' : '↓') : ''}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedPositions.map(pos => <PositionRow key={pos.order_id} position={pos} />)}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
