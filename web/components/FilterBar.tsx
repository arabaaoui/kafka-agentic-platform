"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Filter } from "lucide-react";
import clsx from "clsx";

interface FilterBarProps {
  envs: string[];
  statuses: string[];
  currentEnv?: string;
  currentStatus?: string;
}

export function FilterBar({ envs, statuses, currentEnv, currentStatus }: FilterBarProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const updateFilter = (key: string, value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set(key, value);
    } else {
      params.delete(key);
    }
    params.set("page", "1"); // Reset to page 1 on filter change
    router.push(`?${params.toString()}`);
  };

  return (
    <div className="flex flex-wrap items-center gap-4">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-xl">
        <Filter className="w-3.5 h-3.5 text-slate-500" />
        <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Filters</span>
      </div>

      <select
        value={currentEnv || ""}
        onChange={(e) => updateFilter("env", e.target.value)}
        className="bg-slate-900 border border-slate-800 text-slate-300 text-xs rounded-xl px-4 py-1.5 focus:ring-1 focus:ring-blue-500 outline-none transition-all cursor-pointer hover:bg-slate-800"
      >
        <option value="">All Environments</option>
        {envs.map((env) => (
          <option key={env} value={env.toLowerCase()}>
            {env.toUpperCase()}
          </option>
        ))}
      </select>

      <select
        value={currentStatus || ""}
        onChange={(e) => updateFilter("status", e.target.value)}
        className="bg-slate-900 border border-slate-800 text-slate-300 text-xs rounded-xl px-4 py-1.5 focus:ring-1 focus:ring-blue-500 outline-none transition-all cursor-pointer hover:bg-slate-800"
      >
        <option value="">All Statuses</option>
        {statuses.map((status) => (
          <option key={status} value={status.toLowerCase()}>
            {status}
          </option>
        ))}
      </select>

      {(currentEnv || currentStatus) && (
        <button
          onClick={() => {
            const params = new URLSearchParams(searchParams.toString());
            params.delete("env");
            params.delete("status");
            params.set("page", "1");
            router.push(`?${params.toString()}`);
          }}
          className="text-[10px] font-bold text-blue-400 uppercase tracking-widest hover:text-blue-300 transition-colors"
        >
          Clear All
        </button>
      )}
    </div>
  );
}
