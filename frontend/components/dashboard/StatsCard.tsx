export default function StatsCard({ title, value }: { title: string; value: string | number }) {
  return (
    <div className="p-4 border rounded shadow-sm bg-white dark:bg-slate-800">
      <div className="text-sm text-slate-500">{title}</div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  );
}
