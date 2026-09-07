import useSWR from 'swr';
import { fetcher } from '../api/client';
import { evidenceFixtures, evidenceModeEnabled } from '../evidenceMode';

export function useOptionalAiStatus() {
  const { data, error, isLoading } = useSWR(evidenceModeEnabled ? null : '/api/proxy/analytics/optional-ai-status', fetcher, {
    refreshInterval: 60000, dedupingInterval: 30000, errorRetryCount: 2,
  });
  return { optionalAi: evidenceModeEnabled ? evidenceFixtures.optionalAi : data, isLoading: evidenceModeEnabled ? false : isLoading, isError: evidenceModeEnabled ? null : error };
}
