import { getSystemAuditLogs } from "@/lib/api";
import { Shield, ChevronLeft, ChevronRight, Activity, Clock, User } from "lucide-react";
import { AuditFilterBar } from "./AuditFilterBar";
import Link from "next/link";
import clsx from "clsx";

export const revalidate = 0;

export default async function AdminAuditPage({
  searchParams,
}: {
  searchParams: { page?: string; action?: string; resource_type?: string };
}) {
  const page = Number(searchParams.page) || 1;
  const limit = 30;
  const offset = (page - 1) * limit;

  let data;
  try {
    data = await getSystemAuditLogs({ 
      limit, 
      offset, 
      action: searchParams.action,
      resourceType: searchParams.resource_type
    });
  } catch (err) {
    return (
      <div className="p-8 bg-red-500/5 border border-red-500/20 rounded-2xl text-red-400 text-sm flex items-center gap-3">
        <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
        Could not load audit logs.
      </div>
    );
  }

  const ACTIONS = ["DELETE_MISSION", "DELETE_KB_CARD", "RELOAD_TENANTS"];
  const RESOURCES = ["MISSION", "KB_CARD", "TENANT"];
  const totalPages = Math.ceil(data.total / limit);

  return (
    <div className="space-y-8">
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3 tracking-tight">
            <Shield className="w-6 h-6 text-blue-500" />
            Platform Audit Trail
          </h1>
          <p className="text-slate-500 text-sm mt-1">Traceability of all destructive and administrative actions.</p>
        </div>
        <AuditFilterBar 
          actions={ACTIONS}
          resourceTypes={RESOURCES}
          currentAction={searchParams.action}
          currentResourceType={searchParams.resource_type}
        />
      </header>

      <div className="bg-slate-900/40 border border-slate-800 rounded-2xl overflow-hidden shadow-sm backdrop-blur-sm">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-slate-900/80 border-b border-slate-800">
              <th className="px-6 py-4 text-[10px] font-black text-slate-500 uppercase tracking-widest">Timestamp</th>
              <th className="px-6 py-4 text-[10px] font-black text-slate-500 uppercase tracking-widest">Action</th>
              <th className="px-6 py-4 text-[10px] font-black text-slate-500 uppercase tracking-widest">Resource</th>
              <th className="px-6 py-4 text-[10px] font-black text-slate-500 uppercase tracking-widest">User</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            {data.items.map((audit: any) => (
              <tr key={audit.id} className="hover:bg-blue-500/[0.02] transition-colors group">
                <td className="px-6 py-4">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-slate-300 text-xs font-medium">
                      {new Date(audit.created_at).toLocaleDateString()}
                    </span>
                    <span className="text-slate-500 text-[10px] font-mono">
                      {new Date(audit.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <span className={clsx("inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-black uppercase tracking-wider", {
                    "bg-red-500/10 text-red-400 border-red-500/20": audit.action.startsWith("DELETE"),
                    "bg-blue-500/10 text-blue-400 border-blue-500/20": !audit.action.startsWith("DELETE"),
                  })}>
                    {audit.action}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <div className="flex flex-col gap-1">
                    <span className="text-slate-400 text-[10px] font-black uppercase tracking-widest opacity-50">{audit.resource_type}</span>
                    <span className="text-blue-400 font-mono text-xs">{audit.resource_id}</span>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded-full bg-slate-800 flex items-center justify-center border border-slate-700">
                      <User className="w-3 h-3 text-slate-400" />
                    </div>
                    <span className="text-slate-300 text-xs font-medium">{audit.created_by}</span>
                  </div>
                </td>
              </tr>
            ))}
            {data.items.length === 0 && (
              <tr>
                <td colSpan={4} className="px-6 py-16 text-center text-slate-500 text-sm italic">
                  No audit events matching criteria.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <Pagination page={page} total={totalPages} searchParams={searchParams} />
      )}
    </div>
  );
}

function Pagination({ page, total, searchParams }: { page: number; total: number; searchParams: any }) {
  const p = (n: number) => {
    const params = new URLSearchParams();
    if (searchParams.action) params.set("action", searchParams.action);
    if (searchParams.resource_type) params.set("resource_type", searchParams.resource_type);
    params.set("page", String(n));
    return `/admin/audit?${params.toString()}`;
  };
  
  return (
    <div className="flex justify-center items-center gap-6 text-[11px] font-bold uppercase tracking-widest text-slate-500 pt-6">
      <Link 
        href={page > 1 ? p(page - 1) : "#"} 
        className={clsx("flex items-center gap-1 transition-colors", page > 1 ? "hover:text-blue-400" : "opacity-30 cursor-not-allowed")}
      >
        <ChevronLeft className="w-4 h-4" /> Prev
      </Link>
      <span className="text-slate-400 bg-slate-900 px-3 py-1 rounded-full border border-slate-800">
        Page {page} / {total}
      </span>
      <Link 
        href={page < total ? p(page + 1) : "#"} 
        className={clsx("flex items-center gap-1 transition-colors", page < total ? "hover:text-blue-400" : "opacity-30 cursor-not-allowed")}
      >
        Next <ChevronRight className="w-4 h-4" />
      </Link>
    </div>
  );
}
