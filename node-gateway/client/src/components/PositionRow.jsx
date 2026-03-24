import React from 'react';

export default function PositionRow({ position }) {
  const pnlColor = position.unrealised_pnl >= 0 ? 'text-green-400' : 'text-red-400';
  
  return (
    <tr className="border-b border-gray-700 hover:bg-gray-750 transition-colors">
      <td className="p-3 font-medium text-white">{position.ticker}</td>
      <td className="p-3 font-mono text-gray-300">₹{position.entry_price}</td>
      <td className="p-3 font-mono text-red-400">₹{position.current_stop}</td>
      <td className="p-3 font-mono text-green-400">₹{position.target_1}</td>
      <td className="p-3 font-mono text-green-500">₹{position.target_2}</td>
      <td className={`p-3 font-mono font-bold ${pnlColor}`}>
        {position.unrealised_pnl >= 0 ? '+' : ''}₹{position.unrealised_pnl}
      </td>
      <td className="p-3 text-gray-300">{position.r_multiple}R</td>
      <td className="p-3 text-gray-400">{position.days_held}</td>
      <td className="p-3 text-xs">
        <span className={`px-2 py-1 rounded ${position.source === 'SYSTEM' ? 'bg-purple-900/50 text-purple-300' : 'bg-gray-700 text-gray-300'}`}>
          {position.source}
        </span>
      </td>
    </tr>
  );
}
