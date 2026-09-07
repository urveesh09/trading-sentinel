import useSWR from 'swr';
import { fetcher } from '../api/client';
import { evidenceFixtures, evidenceModeEnabled } from '../evidenceMode';

export function useProactiveActivity() {
  const { data, error, isLoading } = useSWR(evidenceModeEnabled ? null : '/api/proxy/analytics/proactive-activity?days=7', fetcher, {
    refreshInterval: 60000, dedupingInterval: 30000, errorRetryCount: 2,
  });
  return { activity: evidenceModeEnabled ? evidenceFixtures.proactiveActivity : data, isLoading: evidenceModeEnabled ? false : isLoading, isError: evidenceModeEnabled ? null : error };
}
