import useSWR from 'swr';
import { fetcher } from '../api/client';

export function useOperationalCoverage() {
  const state = useSWR('/api/proxy/analytics/operational-coverage', fetcher, {
    refreshInterval: 30000, dedupingInterval: 10000, errorRetryCount: 2,
  });
  return { coverage: state.data, isLoading: state.isLoading, isError: state.error };
}
