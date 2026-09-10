import React from 'react';
import { Activity, Clock, Server, ShieldAlert } from 'lucide-react';
import { useHealth } from '../hooks/useHealth';

export default function StatusBar({ cbHalted }) {
  const { health, isLoading, isError, lastUpdated } = useHealth();

  if (isLoading && !health) return <div className="h-10 bg-gray-900 animate-pulse border-b border-gray-800" />;

  const isMarketOpen = health?.market_open || false;
  const tokenActive = health?.token_status === 'active';
  const engineReachable = health?.python_engine === 'reachable';
  const gatewayRelease = health?.release?.revision;
  const engineRelease = health?.python_engine_release?.revision;
  const releaseMatches = Boolean(
    health?.release?.declared
    && health?.python_engine_release?.declared
    && gatewayRelease === engineRelease
  );

  return (
    <div className="flex flex-wrap items-center justify-between bg-gray-900 px-4 py-2 text-sm text-gray-300 border-b border-gray-800">
      <div className="flex space-x-4">
        {/* Zerodha Token Status */}
        <div className="flex items-center space-x-1">
          <Activity size={16} className={tokenActive ? 'text-green-500' : 'text-red-500'} />
          <span>Zerodha: {tokenActive ? 'Connected' : 'Disconnected'}</span>
        </div>

        {/* Market Status */}
        <div className="flex items-center space-x-1">
          <Clock size={16} className={isMarketOpen ? 'text-green-500' : 'text-yellow-500'} />
          <span>Market: {isMarketOpen ? 'Open' : 'Closed'}</span>
        </div>

        {/* Python Engine Status */}
        <div className="flex items-center space-x-1">
          <Server size={16} className={engineReachable ? 'text-green-500' : 'text-red-500'} />
          <span>Engine: {engineReachable ? 'Online' : 'Unreachable'}</span>
        </div>

        {/* Circuit Breaker Status */}
        <div className="flex items-center space-x-1">
          <ShieldAlert size={16} className={cbHalted ? 'text-red-500' : 'text-green-500'} />
          <span>CB: {cbHalted ? 'HALTED' : 'Normal'}</span>
        </div>

        {/* Runtime liveness cannot prove the deployed commit.  Keep the
            identity visible, but do not imply that an unknown/mismatch is a
            trading gate; the deployment verifier is authoritative. */}
        {gatewayRelease && (
          <div className="flex items-center space-x-1" title="Gateway and engine must show the same reviewed revision before a release is accepted.">
            <Server size={16} className={releaseMatches ? 'text-green-500' : 'text-amber-500'} />
            <span>Release: {gatewayRelease.slice(0, 12)}{releaseMatches ? '' : ' (unverified)'}</span>
          </div>
        )}
      </div>

      {lastUpdated && (
        <div className="text-xs text-gray-500">
          Last updated: {lastUpdated.toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}
