"use client";
import React from 'react';
import { useMetrics, useRecentWorkflows, useRecentContent, useLatestVideos } from '../hooks/useDashboard';
import Loading from '../components/ui/Loading';
import DashboardCards from '../components/dashboard/DashboardCards';
import DashboardCharts from '../components/dashboard/DashboardCharts';
import RecentActivity from '../components/dashboard/RecentActivity';
import RecentResearchTable from '../components/dashboard/RecentResearchTable';

export default function Page() {
  const { data: metrics, isLoading: metricsLoading, error: metricsError } = useMetrics();
  const { data: workflows, isLoading: workflowsLoading, error: workflowsError } = useRecentWorkflows(8);
  const { data: content, isLoading: contentLoading, error: contentError } = useRecentContent(8);
  const { data: videos, isLoading: videosLoading, error: videosError } = useLatestVideos(8);

  const loading = metricsLoading || workflowsLoading || contentLoading || videosLoading;
  const error = metricsError || workflowsError || contentError || videosError;
  const hasError = Boolean(error);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-sm text-slate-500">Overview and statistics</p>
        </div>
      </div>

      {loading && (
        <div className="p-4">
          <Loading />
        </div>
      )}

      {hasError && (
        <div className="p-4 bg-red-50 text-red-700 rounded">Error loading dashboard data. Check API connectivity.</div>
      )}

      {!loading && !hasError && (
        <>
          <DashboardCards metrics={metrics} />
          <DashboardCharts metrics={metrics} />

          <RecentActivity workflows={workflows || []} content={content || []} videos={videos || []} />

          <RecentResearchTable workflows={workflows || []} />
        </>
      )}
    </div>
  );
}
