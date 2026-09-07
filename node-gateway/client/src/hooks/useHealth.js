import useSWR from 'swr';
import { fetcher } from '../api/client';
import { evidenceFixtures, evidenceModeEnabled } from '../evidenceMode';

export function useHealth() {
  // Container A health endpoint (which also probes Container B)
  const { data, error, isLoading } = useSWR(evidenceModeEnabled ? null : '/api/health', fetcher, {
    refreshInterval: 30000, // 30s refresh per spec
    dedupingInterval: 10000,
    errorRetryCount: 3
  });

  return {
    health: evidenceModeEnabled ? evidenceFixtures.health : data,
    isLoading: evidenceModeEnabled ? false : isLoading,
    isError: evidenceModeEnabled ? null : error,
    lastUpdated: (evidenceModeEnabled || data) ? new Date() : null
  };
}
