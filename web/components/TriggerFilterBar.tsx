"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Filter } from "lucide-react";

interface TriggerFilterBarProps {
  sources: string[];
  currentSource?: string;
}

export function TriggerFilterBar({ sources, currentSource }: TriggerFilterBarProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const updateFilter = (value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set("source", value);
    } else {
      params.delete("source");
    }
    params.set("page", "1");
    router.push(`?${params.toString()}`);
  };

  return (
    <div className="flex items-center gap-4">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-xl">
        <Filter className="w-3.5 h-3.5 text-slate-500" />
        <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Source</span>
      </div>

      <select
        value={currentSource || ""}
        onChange={(e) => updateFilter(e.target.value)}
        className="bg-slate-900 border border-slate-800 text-slate-300 text-xs rounded-xl px-4 py-1.5 focus:ring-1 focus:ring-blue-500 outline-none transition-all cursor-pointer hover:bg-slate-800"
      >
        <option value="">All Sources</option>
        {sources.map((s) => (
          <option key={s} value={s.toLowerCase()}>
            {s}
          </option>
        ))}
      </select>

      {currentSource && (
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
