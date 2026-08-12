import api from '../lib/api';

// Normalize and forward research creation payload to backend expected shape
export async function createResearch(payload: any) {
  const body: any = {};
  // map common fields to backend names
  body.keyword = payload.keyword ?? payload.topic ?? payload.query ?? payload.q;
  // prefer explicit max_results, fall back to camelCase or limit
  body.max_results = payload.max_results ?? payload.maxResults ?? payload.limit ?? 50;
  body.limit = payload.limit ?? payload.max_results ?? payload.maxResults ?? 50;
  body.run_title_generation = payload.run_title_generation ?? payload.runTitleGeneration ?? false;
  body.run_content_generation = payload.run_content_generation ?? payload.runContentGeneration ?? false;

  const res = await api.post('/research', body);
  return res.data;
}

export async function listWorkflows(limit = 50) {
  const res = await api.get('/research', { params: { limit } });
  // backend returns { total, items }
  return res.data?.items ?? res.data;
}

export async function getWorkflow(id: string) {
  const res = await api.get(`/research/${id}`);
  return res.data;
}
