import api from '../lib/api';

export interface AnalysisListParams {
  limit?: number;
  offset?: number;
}

export async function fetchAnalyses(params: AnalysisListParams = {}) {
  const res = await api.get('/analysis', { params });
  return res.data;
}
