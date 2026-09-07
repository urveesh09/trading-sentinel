import useSWR from 'swr';
import { fetcher } from '../api/client';

export function usePartnerHedgeCards() {
  const { data, error, isLoading } = useSWR('/api/proxy/partner/hedge/cards?limit=12', fetcher, {
    refreshInterval: 60000, dedupingInterval: 30000, errorRetryCount: 2,
  });
  return { cards: data, isLoading, isError: error };
}
