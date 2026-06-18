import Link from "next/link";
import { listTriggers, listIgnoredTriggers, type Trigger } from "@/lib/api";
import { ChevronLeft, ChevronRight, Zap } from "lucide-react";
import { TriggerFilterBar } from "@/components/TriggerFilterBar";
import clsx from "clsx";

export const revalidate = 0;

interface PageProps {
  searchParams: { tab?: string; page?: string; source?: string };
}

export default async function TriggersPage({ searchParams }: PageProps) {
  const tab = searchParams.tab === "ignored" ? "ignored" : "all";
  const limit = 30;
  const page = Number(searchParams.page ?? 1);
  const offset = (page - 1) * limit;
  const source = searchParams.source;

  let data;
  try {
    data = tab === "ignored"
      ? await listIgnoredTriggers({ limit, offset, source })
      : await listTriggers({ limit, offset, source });
  } catch {
    return (
      <div className="p-8 bg-red-500/5 border border-red-500/20 rounded-2xl text-red-400 text-sm flex items-center gap-3">
        <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
        Could not load triggers — is the API running?
      </div>
    );
  }

  const totalPages = Math.ceil(data.total / limit);
  const SOURCES = ["Jira", "Alertmanager", "Care"];

  return (
    <div className="space-y-8">
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            Triggers
            <span className="text-slate-500 font-normal text-sm bg-slate-900 px-2 py-0.5 rounded-lg border border-slate-800">
              {data.total}
            </span>
          </h1>
          <p className="text-slate-500 text-sm mt-1">Inbound signals from external monitoring and alerting systems.</p>
        </div>
        <div className="flex flex-wrap items-center gap-6">
          <TriggerFilterBar sources={SOURCES} currentSource={source} />
          <TabNav tab={tab} source={source} />
        </div>
      </header>

      {data.items.length === 0 ? (
        <div className="py-24 text-center bg-slate-900/20 border border-slate-800 border-dashed rounded-3xl">
          <Zap className="w-8 h-8 text-slate-700 mx-auto mb-4" />
          <p className="text-slate-500 text-sm italic">
            {tab === "ignored" ? "No ignored triggers." : "No triggers received yet."}
          </p>
        </div>
      ) : (
        <div className="bg-slate-900/40 border border-slate-800 rounded-2xl overflow-hidden shadow-sm backdrop-blur-sm">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-900/80 border-b border-slate-800">
                <th className="px-6 py-4 text-[10px] font-black text-slate-500 uppercase tracking-widest">Source</th>
                <th className="px-6 py-4 text-[10px] font-black text-slate-500 uppercase tracking-widest">External ID</th>
                <th className="px-6 py-4 text-[10px] font-black text-slate-500 uppercase tracking-widest">Tenant</th>
                {tab === "ignored" && <th className="px-6 py-4 text-[10px] font-black text-slate-500 uppercase tracking-widest">Reason</th>}
                <th className="px-6 py-4 text-[10px] font-black text-slate-500 uppercase tracking-widest">Received</th>
                <th className="px-6 py-4 text-[10px] font-black text-slate-500 uppercase tracking-widest text-right">Mission</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {data.items.map((t) => (
                <TriggerRow key={t.id} trigger={t} showReason={tab === "ignored"} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <Pagination page={page} total={totalPages} tab={tab} source={source} />
      )}
    </div>
  );
}

function TriggerRow({ trigger: t, showReason }: { trigger: Trigger; showReason: boolean }) {
  return (
    <tr className="hover:bg-blue-500/[0.02] transition-colors group">
      <td className="px-6 py-4">
        <SourceBadge source={t.source} />
      </td>
      <td className="px-6 py-4">
        <span className="font-mono text-slate-400 text-xs max-w-[200px] truncate block" title={t.external_id}>
          {t.external_id}
        </span>
      </td>
      <td className="px-6 py-4">
        <span className="text-slate-300 text-xs font-medium uppercase">{t.tenant}</span>
      </td>
      {showReason && (
        <td className="px-6 py-4">
          <span className="text-amber-500/80 text-xs max-w-[240px] truncate block" title={t.reject_reason ?? ""}>
            {t.reject_reason ?? "—"}
          </span>
        </td>
      )}
      <td className="px-6 py-4">
        <div className="flex flex-col gap-0.5">
           <span className="text-slate-400 text-[11px]">{new Date(t.received_at).toLocaleDateString()}</span>
           <span className="text-slate-500 text-[10px] font-mono">{new Date(t.received_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
        </div>
      </td>
      <td className="px-6 py-4 text-right">
        {t.mission_id
          ? (
            <Link
              href={`/missions/${encodeURIComponent(t.mission_id)}`}
              className="text-blue-400 hover:text-blue-300 font-mono text-xs font-bold"
            >
              {t.mission_id.slice(0, 12)}…
            </Link>
          )
          : <span className="text-slate-700 text-xs">—</span>}
      </td>
    </tr>
  );
}

function SourceBadge({ source }: { source: string }) {
  const style: Record<string, string> = {
    jira:          "bg-blue-500/10 text-blue-400 border-blue-500/20",
    alertmanager:  "bg-red-500/10 text-red-400 border-red-500/20",
    care:          "bg-violet-500/10 text-violet-400 border-violet-500/20",
  };
  const cls = style[source] ?? "bg-slate-800 text-slate-400 border-slate-700";
  return (
    <span className={clsx("inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-bold uppercase tracking-wider", cls)}>
      {source}
    </span>
  );
}

function TabNav({ tab, source }: { tab: string; source?: string }) {
  const q = (t: string) => {
    const params = new URLSearchParams();
    if (t === "ignored") params.set("tab", "ignored");
    if (source) params.set("source", source);
    const qs = params.toString();
    return `/triggers${qs ? `?${qs}` : ""}`;
  };

  return (
    <div className="flex bg-slate-900 p-1 rounded-xl border border-slate-800">
      <Link
        href={q("all")}
        className={clsx(
          "px-4 py-1.5 rounded-lg text-xs font-bold transition-all",
          tab === "all" ? "bg-slate-800 text-white shadow-sm" : "text-slate-500 hover:text-slate-300"
        )}
      >
        All Received
      </Link>
      <Link
        href={q("ignored")}
        className={clsx(
          "px-4 py-1.5 rounded-lg text-xs font-bold transition-all",
          tab === "ignored" ? "bg-slate-800 text-white shadow-sm" : "text-slate-500 hover:text-slate-300"
        )}
      >
        Ignored
      </Link>
    </div>
  );
}

function Pagination({ page, total, tab, source }: { page: number; total: number; tab: string; source?: string }) {
  const p = (n: number) => {
    const params = new URLSearchParams();
    if (tab === "ignored") params.set("tab", "ignored");
    if (source) params.set("source", source);
    params.set("page", String(n));
    return `/triggers?${params.toString()}`;
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
