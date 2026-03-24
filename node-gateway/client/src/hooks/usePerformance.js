import useSWR from 'swr';
import { fetcher } from '../api/client';

export function usePerformance() {
  const { data, error, isLoading } = useSWR('/api/proxy/performance', fetcher, {
    refreshInterval: 60000, // 60s refresh per spec
    dedupingInterval: 30000,
    errorRetryCount: 3
  });

  return {
    performance: data,
    isLoading,
    isError: error,
    lastUpdated: data ? new Date() : null
  };
}
