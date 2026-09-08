import useSWR from 'swr';
import { fetcher } from '../api/client';
import { evidenceFixtures, evidenceModeEnabled } from '../evidenceMode';

export function useProactiveSessionDiagnostics() {
  const { data, error, isLoading } = useSWR(evidenceModeEnabled ? null : '/api/proxy/analytics/proactive-session-diagnostics?sessions=5', fetcher, {
    refreshInterval: 60000, dedupingInterval: 30000, errorRetryCount: 2,
  });
  return { sessionDiagnostics: evidenceModeEnabled ? evidenceFixtures.sessionDiagnostics : data, isLoading: evidenceModeEnabled ? false : isLoading, isError: evidenceModeEnabled ? null : error };
}
