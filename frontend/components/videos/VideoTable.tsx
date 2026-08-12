"use client";
/* eslint-disable no-unused-vars */
import React, { useState } from 'react';

export default function VideoTable({ data, onSelect }: { data: any[]; onSelect: (id: string) => void }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-slate-500">
              <th className="py-2 pr-4">Thumbnail</th>
              <th className="py-2 pr-4">Title</th>
              <th className="py-2 pr-4">Channel</th>
              <th className="py-2 pr-4">Views</th>
              <th className="py-2 pr-4">Uploaded</th>
              <th className="py-2 pr-4">Duration</th>
              <th className="py-2 pr-4">Transcript</th>
              <th className="py-2 pr-4">Analysis</th>
              <th className="py-2 pr-4">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.map((v: any) => (
              <React.Fragment key={v.id}>
                <tr className="border-t">
                  <td className="py-2 pr-4 w-24">
                    {v.thumbnail_url ? (
                      <img src={v.thumbnail_url} alt={v.title} className="h-12 w-20 object-cover rounded" />
                    ) : (
                      <div className="h-12 w-20 bg-slate-200 dark:bg-slate-700 rounded" />
                    )}
                  </td>
                  <td className="py-2 pr-4 font-medium">{v.title}</td>
                  <td className="py-2 pr-4">{v.channel_name || v.channel}</td>
                  <td className="py-2 pr-4">{v.view_count ?? '-'}</td>
                  <td className="py-2 pr-4">{v.upload_date ? new Date(v.upload_date).toLocaleDateString() : '-'}</td>
                  <td className="py-2 pr-4">{v.duration ? v.duration : v.duration_seconds ? `${Math.floor(v.duration_seconds/60)}:${String(v.duration_seconds%60).padStart(2,'0')}` : '-'}</td>
                  <td className="py-2 pr-4">{v.transcript_available ? 'Yes' : 'No'}</td>
                  <td className="py-2 pr-4">{v.analysis_status ?? '-'}</td>
                  <td className="py-2 pr-4">
                    <div className="flex gap-2">
                      <button className="px-2 py-1 border rounded" onClick={() => onSelect(v.id)}>View</button>
                      <button className="px-2 py-1 border rounded" onClick={() => setExpanded(expanded === v.id ? null : v.id)}>Toggle</button>
                    </div>
                  </td>
                </tr>
                {expanded === v.id && (
                  <tr>
                    <td colSpan={9} className="p-4 bg-slate-50 dark:bg-slate-900">
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                          {v.thumbnail_url ? <img src={v.thumbnail_url} alt={v.title} className="rounded w-full" /> : null}
                        </div>
                        <div className="md:col-span-2">
                          <h4 className="font-semibold">{v.title}</h4>
                          <div className="text-sm text-slate-500">Channel: {v.channel_name || v.channel}</div>
                          <div className="text-sm text-slate-500">Views: {v.view_count ?? '-'}</div>
                          <div className="text-sm text-slate-500">Uploaded: {v.upload_date ? new Date(v.upload_date).toLocaleString() : '-'}</div>
                          <div className="text-sm text-slate-500">Duration: {v.duration ?? '-'}</div>
                          <div className="text-sm text-slate-500">Transcript: {v.transcript_available ? 'Available' : 'Not available'}</div>
                          <div className="text-sm text-slate-500">Analysis: {v.analysis_status ?? 'N/A'}</div>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
