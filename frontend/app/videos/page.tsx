"use client";
import React, { useState } from 'react';
import { useVideos } from '../../hooks/useVideos';
import Loading from '../../components/ui/Loading';
import VideoTable from '../../components/videos/VideoTable';

export default function VideosPage() {
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 12;
  const { data, isLoading, isError } = useVideos(q, page, pageSize);

  const videos = data?.items ?? data?.results ?? data ?? [];
  const total = data?.total ?? data?.count ?? 0;

  const onSelect = (id: string) => {
    // Navigate to detail or expand handled in VideoTable via Toggle
    console.log('select', id);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Videos</h1>
      </div>

      <div className="flex gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search videos" className="border rounded p-2 flex-1" />
        <button className="px-3 py-2 bg-slate-900 text-white rounded" onClick={() => setPage(1)}>Search</button>
      </div>

      <div>
        {isLoading && <Loading />}
        {isError && <div className="text-red-600">Failed to load videos</div>}
        {!isLoading && !isError && (
          <>
            <VideoTable data={videos} onSelect={onSelect} />

            <div className="flex items-center justify-between mt-4">
              <div className="text-sm text-slate-500">Total: {total}</div>
              <div className="flex gap-2">
                <button className="px-3 py-1 border rounded" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>Prev</button>
                <div className="px-3 py-1 border rounded">{page}</div>
                <button className="px-3 py-1 border rounded" onClick={() => setPage((p) => p + 1)} disabled={videos.length < pageSize}>Next</button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
