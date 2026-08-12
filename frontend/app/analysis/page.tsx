"use client";

import { useState } from 'react';
import Loading from '../../components/ui/Loading';
import AnalysisCard from '../../components/analysis/AnalysisCard';
import { useAnalyses } from '../../hooks/useAnalysis';

export default function AnalysisPage() {
  const [page, setPage] = useState(1);
  const pageSize = 6;
  const { data, isLoading, isError, error } = useAnalyses(page, pageSize);

  const analyses = data?.items ?? data?.results ?? data?.analyses ?? [];
  const total = data?.total ?? data?.count ?? analyses.length;
  const totalPages = total ? Math.ceil(total / pageSize) : undefined;
  const canPrev = page > 1;
  const canNext = analyses.length === pageSize && (typeof total !== 'number' || page < (totalPages ?? page + 1));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Analysis</h1>
        <p className="mt-2 text-slate-500">Browse structured video analysis insights and paging through backend results.</p>
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300">
        <div>Showing analysis results from the backend with pagination, loading, error, and empty state handling.</div>
      </div>

      <div>
        {isLoading && <Loading />}
        {isError && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
            <strong className="font-semibold">Failed to load analysis.</strong>
            <p className="mt-1 text-sm">{error instanceof Error ? error.message : 'Please try again later.'}</p>
          </div>
        )}

        {!isLoading && !isError && analyses.length === 0 && (
          <div className="rounded-xl border border-slate-200 bg-white px-6 py-10 text-center text-slate-500 shadow-sm dark:border-slate-700 dark:bg-slate-950 dark:text-slate-400">
            <p className="text-lg font-semibold">No analysis results found.</p>
            <p className="mt-2">Once analysis runs are available, results will appear here.</p>
          </div>
        )}

        {!isLoading && !isError && analyses.length > 0 && (
          <div className="space-y-6">
            <div className="grid gap-6 xl:grid-cols-2">
              {analyses.map((item: any) => (
                <AnalysisCard key={item.video_id ?? item.id ?? item.title ?? Math.random()} item={item} />
              ))}
            </div>

            <div className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4 text-sm dark:border-slate-700 dark:bg-slate-950 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-slate-600 dark:text-slate-300">
                Total results: <span className="font-semibold text-slate-900 dark:text-white">{total}</span>
                {totalPages ? <span> · Page {page} of {totalPages}</span> : null}
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
                  onClick={() => setPage((value) => Math.max(1, value - 1))}
                  disabled={!canPrev}
                >
                  Previous
                </button>
                <span className="text-sm text-slate-500 dark:text-slate-400">Page {page}{totalPages ? ` of ${totalPages}` : ''}</span>
                <button
                  type="button"
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
                  onClick={() => setPage((value) => value + 1)}
                  disabled={!canNext}
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
