/*import useSWR from 'swr';
import { fetcher } from '../api/client';

export function usePositions() {
  const { data, error, isLoading, mutate } = useSWR('/api/proxy/positions', fetcher, {
    refreshInterval: 30000, // 30s refresh per spec
    dedupingInterval: 10000,
    errorRetryCount: 3,
    fallbackData: []
  });

  return {
    positions: data,
    isLoading,
    isError: error,
    lastUpdated: data ? new Date() : null,
    mutate
  };
}
*/
import useSWR from 'swr';
import { fetcher } from '../api/client';

export function usePositions() {
  const { data, error, isLoading, mutate } = useSWR('/api/proxy/positions', fetcher, {
    refreshInterval: 30000,
    dedupingInterval: 10000,
    errorRetryCount: 3
  });

  return {
    // CRITICAL FIX: Force it to always be an array, no matter what Python sends
    positions: Array.isArray(data) ? data : (data?.data || []),
    isLoading,
    isError: error,
    lastUpdated: data ? new Date() : null,
    mutate
  };
}
