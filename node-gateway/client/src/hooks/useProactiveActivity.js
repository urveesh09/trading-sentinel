import useSWR from 'swr';
import { fetcher } from '../api/client';

export function useProactiveActivity() {
  const { data, error, isLoading } = useSWR('/api/proxy/analytics/proactive-activity?days=7', fetcher, {
    refreshInterval: 60000, dedupingInterval: 30000, errorRetryCount: 2,
  });
  return { activity: data, isLoading, isError: error };
}
