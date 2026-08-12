import api from '../lib/api';

export interface ContentGenerationRequest {
  topic: string;
  audience: string;
  niche: string;
  knowledge_base?: Array<Record<string, unknown>>;
  pattern_report?: Record<string, unknown>;
  generated_titles?: Array<Record<string, unknown>>;
  trend_info?: unknown;
}

export async function generateContentPackage(payload: ContentGenerationRequest) {
  const res = await api.post('/content', payload);
  return res.data;
}
