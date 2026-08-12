"use client";

import Loading from '../../components/ui/Loading';
import DashboardCards from '../../components/dashboard/DashboardCards';
import DashboardCharts from '../../components/dashboard/DashboardCharts';
import { useMetrics } from '../../hooks/useDashboard';

export default function AnalyticsPage() {
  const { data: metrics, isLoading, isError, error } = useMetrics();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Analytics</h1>
        <p className="mt-2 text-slate-500">View system and workflow metrics powered by the backend analytics endpoint.</p>
      </div>

      {isLoading && <Loading />}

      {isError && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
          <strong className="font-semibold">Failed to load analytics.</strong>
          <p className="mt-1 text-sm">{error instanceof Error ? error.message : 'Please try again later.'}</p>
        </div>
      )}

      {!isLoading && !isError && metrics && (
        <>
          <DashboardCards metrics={metrics} />
          <DashboardCharts metrics={metrics} />
        </>
      )}
    </div>
  );
}
