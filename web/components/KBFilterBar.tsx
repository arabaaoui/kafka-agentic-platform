"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Filter } from "lucide-react";

interface KBFilterBarProps {
  themes: string[];
  currentTheme?: string;
}

export function KBFilterBar({ themes, currentTheme }: KBFilterBarProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const updateFilter = (value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set("theme", value);
    } else {
      params.delete("theme");
    }
    params.set("page", "1");
    router.push(`?${params.toString()}`);
  };

  return (
    <div className="flex items-center gap-4">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-xl">
        <Filter className="w-3.5 h-3.5 text-slate-500" />
        <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Theme</span>
      </div>

      <select
        value={currentTheme || ""}
        onChange={(e) => updateFilter(e.target.value)}
        className="bg-slate-900 border border-slate-800 text-slate-300 text-xs rounded-xl px-4 py-1.5 focus:ring-1 focus:ring-blue-500 outline-none transition-all cursor-pointer hover:bg-slate-800"
      >
        <option value="">All Themes</option>
        {themes.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>

      {currentTheme && (
        <button
          onClick={() => updateFilter("")}
          className="text-[10px] font-bold text-blue-400 uppercase tracking-widest hover:text-blue-300 transition-colors"
        >
          Clear
        </button>
      )}
    </div>
  );
}
