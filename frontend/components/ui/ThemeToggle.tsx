"use client";
import { Sun, Moon } from 'lucide-react';
import { useState, useEffect } from 'react';

export default function ThemeToggle() {
  const [isDark, setIsDark] = useState(false);
  useEffect(() => {
    setIsDark(document.documentElement.classList.contains('dark'));
  }, []);

  const toggle = () => {
    const next = !isDark;
    document.documentElement.classList.toggle('dark', next);
    localStorage.setItem('theme', next ? 'dark' : 'light');
    setIsDark(next);
  };

  return (
    <button onClick={toggle} className="p-2 rounded hover:bg-slate-100 dark:hover:bg-slate-800">
      {isDark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}
