"use client";
import { useQuery } from '@tanstack/react-query';
import { fetchMetrics, fetchRecentWorkflows, fetchRecentContent, fetchLatestVideos } from '../services/dashboardClient';

export function useMetrics() {
  return useQuery(['metrics'], () => fetchMetrics(), { staleTime: 1000 * 30 });
}

export function useRecentWorkflows(limit = 10) {
  return useQuery(['recent-workflows', limit], () => fetchRecentWorkflows(limit), { staleTime: 1000 * 10 });
}

export function useRecentContent(limit = 10) {
  return useQuery(['recent-content', limit], () => fetchRecentContent(limit), { staleTime: 1000 * 10 });
}

export function useLatestVideos(limit = 10) {
  return useQuery(['latest-videos', limit], () => fetchLatestVideos(limit), { staleTime: 1000 * 10 });
}
