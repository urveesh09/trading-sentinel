import useSWR from 'swr';
import { fetcher } from '../api/client';

export function useDivisionPerformance() {
  const { data, error, isLoading } = useSWR('/api/proxy/performance/divisions', fetcher, {
    refreshInterval: 60000,
    dedupingInterval: 30000,
    errorRetryCount: 3,
  });

  return {
    divisionPerformance: data,
    isLoading,
    isError: error,
    lastUpdated: data ? new Date() : null,
  };
}
