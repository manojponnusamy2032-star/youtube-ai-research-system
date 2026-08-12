import api from '../lib/api';

export async function fetchPatterns() {
  const res = await api.get('/patterns');
  return res.data;
}
