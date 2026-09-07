import useSWR from 'swr';
import { fetcher } from '../api/client';

const swrOptions = { refreshInterval: 60000, dedupingInterval: 30000, errorRetryCount: 3 };

export function useResearchExperiments() {
  const momentum = useSWR('/api/proxy/experiments/momentum', fetcher, swrOptions);
  const penny = useSWR('/api/proxy/experiments/penny', fetcher, swrOptions);
  const fno = useSWR('/api/proxy/experiments/fno-opening-range', fetcher, swrOptions);
  const readiness = useSWR('/api/proxy/research/promotion-readiness', fetcher, swrOptions);
  const proactiveComparison = useSWR('/api/proxy/analytics/proactive-comparison?days=90', fetcher, swrOptions);
  const proactiveResearchComparison = useSWR('/api/proxy/analytics/proactive-research-comparison', fetcher, swrOptions);
  return {
    payloads: { momentum: momentum.data, penny: penny.data, fno: fno.data },
    errors: { momentum: momentum.error, penny: penny.error, fno: fno.error },
    readiness: readiness.data,
    readinessError: readiness.error,
    proactiveComparison: proactiveComparison.data,
    proactiveComparisonError: proactiveComparison.error,
    proactiveResearchComparison: proactiveResearchComparison.data,
    proactiveResearchComparisonError: proactiveResearchComparison.error,
    isLoading: [momentum, penny, fno, readiness, proactiveComparison, proactiveResearchComparison].some((item) => item.isLoading && !item.data),
  };
}
