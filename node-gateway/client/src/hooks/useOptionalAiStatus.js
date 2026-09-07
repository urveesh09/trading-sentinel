import useSWR from 'swr';
import { fetcher } from '../api/client';

export function useOptionalAiStatus() {
  const { data, error, isLoading } = useSWR('/api/proxy/analytics/optional-ai-status', fetcher, {
    refreshInterval: 60000, dedupingInterval: 30000, errorRetryCount: 2,
  });
  return { optionalAi: data, isLoading, isError: error };
}
