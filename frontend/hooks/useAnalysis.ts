"use client";

import { useQuery } from '@tanstack/react-query';
import { fetchAnalyses, AnalysisListParams } from '../services/analysisClient';

export function useAnalyses(page = 1, pageSize = 10) {
  const offset = Math.max(0, (page - 1) * pageSize);
  const params: AnalysisListParams = { limit: pageSize, offset };

  return useQuery(['analyses', page, pageSize], () => fetchAnalyses(params), {
    keepPreviousData: true,
    staleTime: 1000 * 10,
  });
}
