import useSWR from 'swr';
import { fetcher } from '../api/client';
import { evidenceFixtures, evidenceModeEnabled } from '../evidenceMode';

export function usePartnerHedgeCards() {
  const { data, error, isLoading } = useSWR(evidenceModeEnabled ? null : '/api/proxy/partner/hedge/cards?limit=12', fetcher, {
    refreshInterval: 60000, dedupingInterval: 30000, errorRetryCount: 2,
  });
  return { cards: evidenceModeEnabled ? evidenceFixtures.partnerCards : data, isLoading: evidenceModeEnabled ? false : isLoading, isError: evidenceModeEnabled ? null : error };
}
