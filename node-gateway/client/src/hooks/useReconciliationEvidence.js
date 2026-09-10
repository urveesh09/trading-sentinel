import useSWR from 'swr';
import { fetcher } from '../api/client';

export function useReconciliationEvidence() {
  const state = useSWR('/api/proxy/analytics/reconciliation-evidence?limit=100', fetcher, {
    refreshInterval: 60000, dedupingInterval: 15000, errorRetryCount: 2,
  });
  return { reconciliationEvidence: state.data, isLoading: state.isLoading, isError: state.error };
}
