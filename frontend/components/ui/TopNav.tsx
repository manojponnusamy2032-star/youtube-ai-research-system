"use client";
import ThemeToggle from './ThemeToggle';

export default function TopNav() {
  return (
    <nav className="w-full border-b p-4 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <h2 className="text-lg font-semibold">YAIRS</h2>
        <div className="text-sm text-muted-foreground">Dashboard</div>
      </div>
      <div className="flex items-center gap-4">
        <ThemeToggle />
      </div>
    </nav>
  );
}
