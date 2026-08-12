"use client";
import { useQuery } from '@tanstack/react-query';
import { fetchVideos } from '../services/videoClient';

export function useVideos(q: string, page: number, pageSize: number) {
  const offset = (page - 1) * pageSize;
  return useQuery(['videos', q, page, pageSize], () => fetchVideos({ q, limit: pageSize, offset }), {
    keepPreviousData: true,
    staleTime: 1000 * 10,
  });
}
