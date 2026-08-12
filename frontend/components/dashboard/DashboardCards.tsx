"use client";
import React from 'react';

export default function DashboardCards({ metrics }: { metrics: any }) {
  const totalVideos = metrics?.total_videos ?? 0;
  const totalChannels = metrics?.total_channels ?? 0;
  const totalResearch = metrics?.total_research_runs ?? 0;
  const totalAnalyses = metrics?.total_analyses ?? 0;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <div className="p-4 rounded shadow bg-white dark:bg-slate-800">
        <div className="text-sm text-slate-500">Total Videos</div>
        <div className="text-2xl font-bold">{totalVideos}</div>
      </div>
      <div className="p-4 rounded shadow bg-white dark:bg-slate-800">
        <div className="text-sm text-slate-500">Total Channels</div>
        <div className="text-2xl font-bold">{totalChannels}</div>
      </div>
      <div className="p-4 rounded shadow bg-white dark:bg-slate-800">
        <div className="text-sm text-slate-500">Research Runs</div>
        <div className="text-2xl font-bold">{totalResearch}</div>
      </div>
      <div className="p-4 rounded shadow bg-white dark:bg-slate-800">
        <div className="text-sm text-slate-500">Analyses</div>
        <div className="text-2xl font-bold">{totalAnalyses}</div>
      </div>
    </div>
  );
}
