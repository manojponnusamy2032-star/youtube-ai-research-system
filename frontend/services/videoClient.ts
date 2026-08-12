import api from '../lib/api';

export async function fetchVideos(params: { q?: string; limit?: number; offset?: number } = {}) {
  const res = await api.get('/videos', { params });
  return res.data;
}

export async function getVideo(id: string) {
  const res = await api.get(`/videos/${id}`);
  return res.data;
}
