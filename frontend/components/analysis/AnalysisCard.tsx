type AnalysisItem = {
  id?: string;
  video_id?: string;
  title?: string;
  video_title?: string;
  hook_type?: string;
  hook?: string;
  emotion?: string;
  viral_score?: number | string;
  confidence_score?: number | string;
  story_structure?: string;
  retention_techniques?: string | string[];
  thumbnail_pattern?: string;
  thumbnail_psychology?: string;
};

function renderListValue(value: string | string[] | undefined) {
  if (!value || (Array.isArray(value) && value.length === 0)) {
    return '-';
  }
  return Array.isArray(value) ? value.join(', ') : value;
}

export default function AnalysisCard({ item }: { item: AnalysisItem }) {
  const hook = item.hook_type ?? item.hook ?? '-';
  const emotion = item.emotion ?? '-';
  const viralScore = item.viral_score ?? item.confidence_score ?? '-';
  const storyStructure = item.story_structure ?? '-';
  const retention = renderListValue(item.retention_techniques);
  const thumbnail = item.thumbnail_pattern ?? item.thumbnail_psychology ?? '-';
  const title = item.title ?? item.video_title ?? item.video_id ?? 'Untitled analysis';

  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md dark:border-slate-700 dark:bg-slate-900">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium text-slate-500">Analysis</p>
          <h2 className="mt-1 text-lg font-semibold text-slate-900 dark:text-white">{title}</h2>
        </div>
        <div className="rounded-2xl bg-slate-100 px-3 py-2 text-right text-sm font-semibold text-slate-900 dark:bg-slate-800 dark:text-slate-100">
          <div className="text-xs text-slate-500">Viral Score</div>
          <div className="mt-1 text-xl">{viralScore}</div>
        </div>
      </div>

      <dl className="mt-5 grid gap-4 sm:grid-cols-2">
        <div className="rounded-2xl bg-slate-50 p-4 text-sm dark:bg-slate-950">
          <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Hook</dt>
          <dd className="mt-2 text-sm text-slate-900 dark:text-slate-100">{hook}</dd>
        </div>
        <div className="rounded-2xl bg-slate-50 p-4 text-sm dark:bg-slate-950">
          <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Emotion</dt>
          <dd className="mt-2 text-sm text-slate-900 dark:text-slate-100">{emotion}</dd>
        </div>
        <div className="rounded-2xl bg-slate-50 p-4 text-sm dark:bg-slate-950">
          <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Story Structure</dt>
          <dd className="mt-2 text-sm text-slate-900 dark:text-slate-100">{storyStructure}</dd>
        </div>
        <div className="rounded-2xl bg-slate-50 p-4 text-sm dark:bg-slate-950">
          <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Retention Technique</dt>
          <dd className="mt-2 text-sm text-slate-900 dark:text-slate-100">{retention}</dd>
        </div>
        <div className="sm:col-span-2 rounded-2xl bg-slate-50 p-4 text-sm dark:bg-slate-950">
          <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Thumbnail Psychology</dt>
          <dd className="mt-2 text-sm text-slate-900 dark:text-slate-100">{thumbnail}</dd>
        </div>
      </dl>
    </article>
  );
}
