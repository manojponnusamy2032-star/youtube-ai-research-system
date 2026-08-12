"use client";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, BarChart, Bar, PieChart, Pie, Cell, Legend } from 'recharts';
import React from 'react';

export default function DashboardCharts({ metrics }: { metrics: any }) {
  const researchOverTime = metrics?.research_over_time ?? [];
  const viralDist = metrics?.viral_score_distribution ?? [];
  const topHooks = metrics?.top_hooks ?? [];
  const topEmotions = metrics?.top_emotions ?? [];

  const COLORS = ['#4F46E5', '#06B6D4', '#F59E0B', '#EF4444', '#10B981', '#8B5CF6'];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
      <div className="p-4 rounded shadow bg-white dark:bg-slate-800">
        <h3 className="font-semibold mb-2">Research Over Time</h3>
        <div style={{ height: 220 }}>
          <ResponsiveContainer>
            <LineChart data={researchOverTime}>
              <XAxis dataKey="date" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="count" stroke="#4F46E5" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="p-4 rounded shadow bg-white dark:bg-slate-800">
        <h3 className="font-semibold mb-2">Viral Score Distribution</h3>
        <div style={{ height: 220 }}>
          <ResponsiveContainer>
            <BarChart data={viralDist}>
              <XAxis dataKey="bucket" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="count" fill="#06B6D4" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="p-4 rounded shadow bg-white dark:bg-slate-800">
        <h3 className="font-semibold mb-2">Top Hook Types</h3>
        <div style={{ height: 220 }}>
          <ResponsiveContainer>
            <PieChart>
              <Pie data={topHooks} dataKey="count" nameKey="hook" cx="50%" cy="50%" outerRadius={70} fill="#8884d8">
                {topHooks.map((entry: any, index: number) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Legend />
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="p-4 rounded shadow bg-white dark:bg-slate-800">
        <h3 className="font-semibold mb-2">Top Emotions</h3>
        <div style={{ height: 220 }}>
          <ResponsiveContainer>
            <PieChart>
              <Pie data={topEmotions} dataKey="count" nameKey="emotion" cx="50%" cy="50%" outerRadius={70}>
                {topEmotions.map((entry: any, index: number) => (
                  <Cell key={`cell2-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Legend />
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
