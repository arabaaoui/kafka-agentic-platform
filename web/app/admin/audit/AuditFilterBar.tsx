"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Filter } from "lucide-react";

interface AuditFilterBarProps {
  actions: string[];
  resourceTypes: string[];
  currentAction?: string;
  currentResourceType?: string;
}

export function AuditFilterBar({ 
  actions, 
  resourceTypes, 
  currentAction, 
  currentResourceType 
}: AuditFilterBarProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const updateFilter = (key: string, value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set(key, value);
    } else {
      params.delete(key);
    }
    params.set("page", "1");
    router.push(`?${params.toString()}`);
  };

  return (
    <div className="flex flex-wrap items-center gap-4">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-xl">
        <Filter className="w-3.5 h-3.5 text-slate-500" />
        <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Filters</span>
      </div>

      <select
        value={currentAction || ""}
        onChange={(e) => updateFilter("action", e.target.value)}
        className="bg-slate-900 border border-slate-800 text-slate-300 text-xs rounded-xl px-4 py-1.5 focus:ring-1 focus:ring-blue-500 outline-none transition-all cursor-pointer hover:bg-slate-800"
      >
        <option value="">All Actions</option>
        {actions.map((a) => (
          <option key={a} value={a.toLowerCase()}>
            {a}
          </option>
        ))}
      </select>

      <select
        value={currentResourceType || ""}
        onChange={(e) => updateFilter("resource_type", e.target.value)}
        className="bg-slate-900 border border-slate-800 text-slate-300 text-xs rounded-xl px-4 py-1.5 focus:ring-1 focus:ring-blue-500 outline-none transition-all cursor-pointer hover:bg-slate-800"
      >
        <option value="">All Resources</option>
        {resourceTypes.map((r) => (
          <option key={r} value={r.toLowerCase()}>
            {r}
          </option>
        ))}
      </select>

      {(currentAction || currentResourceType) && (
        <button
          onClick={() => {
            const params = new URLSearchParams();
            params.set("page", "1");
            router.push(`/admin/audit?${params.toString()}`);
          }}
          className="text-[10px] font-bold text-blue-400 uppercase tracking-widest hover:text-blue-300 transition-colors"
        >
          Clear
        </button>
      )}
    </div>
  );
}
