"use client";
import React from 'react';

export default function RecentResearchTable({ workflows }: { workflows: any[] }) {
  return (
    <div className="p-4 rounded shadow bg-white dark:bg-slate-800">
      <h3 className="font-semibold mb-4">Recent Research</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-slate-500">
              <th className="py-2 pr-4">Topic</th>
              <th className="py-2 pr-4">Status</th>
              <th className="py-2 pr-4">Created At</th>
              <th className="py-2 pr-4">Duration</th>
            </tr>
          </thead>
          <tbody>
            {workflows?.length ? (
              workflows.map((w: any) => (
                <tr key={w.id} className="border-t">
                  <td className="py-2 pr-4">{w.topic || w.payload?.topic || 'Untitled'}</td>
                  <td className="py-2 pr-4">{w.status}</td>
                  <td className="py-2 pr-4">{new Date(w.created_at).toLocaleString()}</td>
                  <td className="py-2 pr-4">{w.duration_seconds ? `${Math.round(w.duration_seconds / 60)}m` : '-'}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={4} className="py-4 text-slate-500">No recent research runs</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
