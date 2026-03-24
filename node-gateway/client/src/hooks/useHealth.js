import useSWR from 'swr';
import { fetcher } from '../api/client';

export function useHealth() {
  // Container A health endpoint (which also probes Container B)
  const { data, error, isLoading } = useSWR('/api/health', fetcher, {
    refreshInterval: 30000, // 30s refresh per spec
    dedupingInterval: 10000,
    errorRetryCount: 3
  });

  return {
    health: data,
    isLoading,
    isError: error,
    lastUpdated: data ? new Date() : null
  };
}
