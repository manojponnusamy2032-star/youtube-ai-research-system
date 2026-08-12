"use client";

import { useMemo, useState } from 'react';
import Loading from '../../components/ui/Loading';
import { usePatterns } from '../../hooks/usePatterns';

const categoryOptions = [
  { value: 'all', label: 'All Patterns' },
  { value: 'hooks', label: 'Hook Types' },
  { value: 'emotions', label: 'Emotions' },
  { value: 'stories', label: 'Story Structures' },
  { value: 'titles', label: 'Title Formulas' },
  { value: 'thumbnails', label: 'Thumbnail Psychology' },
  { value: 'retention', label: 'Retention Techniques' },
];

type PatternEntry = {
  category: string;
  label: string;
  value: string;
  score: number;
};

export default function PatternsPage() {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');
  const { data, isLoading, isError, error } = usePatterns();

  const report = useMemo(() => data?.report ?? {}, [data]);

  const flattenedPatterns = useMemo<PatternEntry[]>(() => {
    if (!report) return [];

    const items: PatternEntry[] = [];

    const addItems = (categoryLabel: string, labelPrefix: string, dataObject: Record<string, number> | undefined) => {
      if (!dataObject) return;
      Object.entries(dataObject).forEach(([itemLabel, score]) => {
        items.push({ category: categoryLabel, label: `${labelPrefix}: ${itemLabel}`, value: itemLabel, score });
      });
    };

    addItems('Hook Types', 'Hook', report.hooks);
    addItems('Emotions', 'Emotion', report.emotions);
    addItems('Story Structures', 'Story', report.stories);
    addItems('Title Formulas', 'Title Formula', report.titles);
    addItems('Thumbnail Psychology', 'Thumbnail', report.thumbnail_psychology);
    addItems('Retention Techniques', 'Retention', report.retention);

    return items.sort((a, b) => b.score - a.score);
  }, [report]);

  const filteredPatterns = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return flattenedPatterns.filter((item) => {
      if (category !== 'all' && item.category.toLowerCase().replace(/\s+/g, '_') !== category) {
        return false;
      }
      if (!normalized) return true;
      return item.label.toLowerCase().includes(normalized) || item.category.toLowerCase().includes(normalized);
    });
  }, [category, flattenedPatterns, query]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Patterns</h1>
        <p className="mt-2 text-slate-500">Explore aggregated pattern insights extracted from video analysis.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-[1fr_auto]">
        <div className="flex flex-col gap-2">
          <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Search Patterns</label>
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by pattern name or category"
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-200 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-800"
          />
        </div>

        <div className="flex flex-col gap-2">
          <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Filter Category</label>
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-200 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-800"
          >
            {categoryOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm">Pattern report generated from backend pattern service.</p>
          <p className="text-sm text-slate-500">Analyzed videos: {report.videos_analyzed ?? '—'}</p>
        </div>
      </div>

      {isLoading && <Loading />}

      {isError && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
          <strong className="font-semibold">Unable to load patterns.</strong>
          <p className="mt-1 text-sm">{error instanceof Error ? error.message : 'Please check your connection and try again.'}</p>
        </div>
      )}

      {!isLoading && !isError && filteredPatterns.length === 0 && (
        <div className="rounded-xl border border-slate-200 bg-white px-6 py-10 text-center text-slate-500 shadow-sm dark:border-slate-700 dark:bg-slate-950 dark:text-slate-400">
          <p className="text-lg font-semibold">No matching patterns found.</p>
          <p className="mt-2">Try a different search term or select a broader category.</p>
        </div>
      )}

      {!isLoading && !isError && filteredPatterns.length > 0 && (
        <div className="grid gap-4 xl:grid-cols-2">
          {filteredPatterns.map((pattern) => (
            <div key={`${pattern.category}-${pattern.value}`} className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md dark:border-slate-700 dark:bg-slate-900">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">{pattern.category}</p>
                  <h2 className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{pattern.value}</h2>
                </div>
                <div className="rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold text-slate-800 dark:bg-slate-800 dark:text-slate-100">
                  {pattern.score?.toFixed?.(1) ?? pattern.score}%
                </div>
              </div>
              <p className="mt-4 text-sm text-slate-600 dark:text-slate-300">{pattern.label}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
