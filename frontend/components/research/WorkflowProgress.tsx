export default function WorkflowProgress({ percent = 0 }: { percent?: number }) {
  return (
    <div className="w-full bg-slate-100 dark:bg-slate-800 rounded overflow-hidden">
      <div style={{ width: `${percent}%` }} className="h-3 bg-slate-900 dark:bg-slate-200 transition-all" />
    </div>
  );
}
