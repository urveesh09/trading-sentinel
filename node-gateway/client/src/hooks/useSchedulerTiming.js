import useSWR from 'swr';
import { fetcher } from '../api/client';

export function useSchedulerTiming() {
  const state = useSWR('/api/proxy/analytics/scheduler-timing?limit=250', fetcher, {
    refreshInterval: 30000, dedupingInterval: 10000, errorRetryCount: 2,
  });
  return { schedulerTiming: state.data, isLoading: state.isLoading, isError: state.error };
}
