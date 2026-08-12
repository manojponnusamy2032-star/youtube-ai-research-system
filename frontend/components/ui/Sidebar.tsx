"use client";
import Link from 'next/link';

export default function Sidebar() {
  const nav = [
    ['Dashboard', '/'],
    ['Research', '/research'],
    ['Videos', '/videos'],
    ['Analysis', '/analysis'],
    ['Patterns', '/patterns'],
    ['Content', '/content'],
    ['Analytics', '/analytics'],
    ['Settings', '/settings'],
  ];

  return (
    <aside className="w-60 border-r p-4 hidden md:block">
      <div className="mb-6">
        <h3 className="text-lg font-bold">YAIRS</h3>
      </div>
      <nav className="space-y-2">
        {nav.map(([label, href]) => (
          <Link key={String(href)} href={String(href)} className="block px-2 py-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800">
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
