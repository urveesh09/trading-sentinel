import useSWR from 'swr';
import { fetcher } from '../api/client';
import { evidenceModeEnabled } from '../evidenceMode';

export function usePartnerDeliveryBacklog() {
  const { data, error, isLoading } = useSWR(
    evidenceModeEnabled ? null : '/api/proxy/partner/hedge/delivery-backlog', fetcher,
    { refreshInterval: 60000, dedupingInterval: 30000, errorRetryCount: 2 },
  );
  return {
    backlog: evidenceModeEnabled ? { manual_recovery: [], quarantine: [] } : data,
    isLoading: evidenceModeEnabled ? false : isLoading,
    isError: evidenceModeEnabled ? null : error,
  };
}
