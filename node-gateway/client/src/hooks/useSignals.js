/*
import useSWR from 'swr';
import { fetcher } from '../api/client';

export function useSignals() {
  const { data, error, isLoading, mutate } = useSWR('/api/proxy/signals', fetcher, {
    refreshInterval: 15000, // 15s refresh per spec
    dedupingInterval: 5000,
    errorRetryCount: 3,
    fallbackData: []
  });

  return {
    signals: data,
    isLoading,
    isError: error,
    lastUpdated: data ? new Date() : null,
    mutate
  };
}
*/
import useSWR from 'swr';
import { fetcher } from '../api/client';

export function useSignals() {
  const { data, error, isLoading, mutate } = useSWR('/api/proxy/signals', fetcher, {
    refreshInterval: 15000,
    dedupingInterval: 5000,
    errorRetryCount: 3
    // Removed the misleading fallbackData
  });

  return {
    // CRITICAL FIX: Safely extract the array from the PortfolioResponse envelope
    signals: data?.signals || [], 
    // Pass the rest of the envelope in case the UI needs bankroll stats from here
    portfolioData: data || null,
    isLoading,
    isError: error,
    lastUpdated: data ? new Date() : null,
    mutate
  };
}
