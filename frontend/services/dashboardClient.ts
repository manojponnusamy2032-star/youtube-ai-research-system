import api from '../lib/api';

export async function fetchMetrics() {
  const res = await api.get('/metrics');
  return res.data;
}

export async function fetchRecentWorkflows(limit = 10) {
  const res = await api.get('/research', { params: { limit } });
  return res.data;
}

export async function fetchRecentContent(limit = 10) {
  const res = await api.get('/content', { params: { limit } });
  return res.data;
}

export async function fetchLatestVideos(limit = 10) {
  const res = await api.get('/videos', { params: { limit } });
  return res.data;
}
