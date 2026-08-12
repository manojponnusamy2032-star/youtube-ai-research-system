"use client";
import React from 'react';

export default function RecentActivity({ workflows, content, videos }: { workflows: any[]; content: any[]; videos: any[] }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
      <div className="p-4 rounded shadow bg-white dark:bg-slate-800">
        <h4 className="font-semibold mb-2">Recent Workflows</h4>
        <ul className="space-y-2">
          {workflows?.length ? (
            workflows.map((w: any) => (
              <li key={w.id} className="text-sm">
                <div className="font-medium">{w.topic || w.payload?.topic || 'Untitled'}</div>
                <div className="text-xs text-slate-500">{w.status} • {new Date(w.created_at).toLocaleString()}</div>
              </li>
            ))
          ) : (
            <li className="text-sm text-slate-500">No recent workflows</li>
          )}
        </ul>
      </div>

      <div className="p-4 rounded shadow bg-white dark:bg-slate-800">
        <h4 className="font-semibold mb-2">Recent Generated Content</h4>
        <ul className="space-y-2">
          {content?.length ? (
            content.map((c: any) => (
              <li key={c.id} className="text-sm">
                <div className="font-medium">{c.topic || c.title || 'Generated'}</div>
                <div className="text-xs text-slate-500">{new Date(c.created_at).toLocaleString()}</div>
              </li>
            ))
          ) : (
            <li className="text-sm text-slate-500">No generated content</li>
          )}
        </ul>
      </div>

      <div className="p-4 rounded shadow bg-white dark:bg-slate-800">
        <h4 className="font-semibold mb-2">Latest Videos</h4>
        <ul className="space-y-2">
          {videos?.length ? (
            videos.map((v: any) => (
              <li key={v.id} className="text-sm">
                <div className="font-medium">{v.title || 'Untitled'}</div>
                <div className="text-xs text-slate-500">{v.channel_name || v.channel || ''}</div>
              </li>
            ))
          ) : (
            <li className="text-sm text-slate-500">No recent videos</li>
          )}
        </ul>
      </div>
    </div>
  );
}
