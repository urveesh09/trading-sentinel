import useSWR from 'swr';
import { fetcher } from '../api/client';

export function usePartnerAdvisorySetup() {
  const state = useSWR('/api/proxy/partner/advisory/setup', fetcher, {
    refreshInterval: 30000, dedupingInterval: 10000, errorRetryCount: 2,
  });
  return { setup: state.data, isLoading: state.isLoading, isError: state.error, mutate: state.mutate };
}
