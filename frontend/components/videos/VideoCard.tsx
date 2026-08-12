export default function VideoCard({ title }: { title: string }) {
  return (
    <div className="p-4 border rounded">
      <div className="font-semibold">{title}</div>
      <div className="text-sm text-slate-500">Duration: 10:23</div>
    </div>
  );
}
