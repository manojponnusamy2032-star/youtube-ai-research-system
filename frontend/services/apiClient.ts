import api from '../lib/api';

export async function fetchHealth() {
  const res = await api.get('/health');
  return res.data;
}

export async function postResearch(payload: any) {
  const res = await api.post('/research', payload);
  return res.data;
}
