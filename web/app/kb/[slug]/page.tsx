import { notFound } from "next/navigation";
import Link from "next/link";
import { AuditViewer } from "@/components/AuditViewer";
import { EnvBadge } from "@/components/EnvBadge";
import { 
  ChevronLeft, 
  Calendar, 
  Hash, 
  Tag, 
  AlertTriangle, 
  Layers,
  Activity
} from "lucide-react";
import matter from "gray-matter";
import clsx from "clsx";

export const revalidate = 60;

interface PageProps {
  params: { slug: string };
}

async function fetchCard(slug: string): Promise<string | null> {
  try {
    const res = await fetch(
      `${process.env.API_INTERNAL_URL ?? "http://backend:8000"}/v1/kb/cards/${encodeURIComponent(slug)}`,
      { cache: "no-store" }
    );
    if (res.status === 404) return null;
    if (!res.ok) return null;
    return await res.text();
  } catch {
    return null;
  }
}

export default async function KBCardPage({ params }: PageProps) {
  const slug = decodeURIComponent(params.slug);
  const rawContent = await fetchCard(slug);

  if (rawContent === null) notFound();

  const { data: meta, content } = matter(rawContent);

  return (
    <div className="space-y-10 max-w-5xl mx-auto">
      {/* Navigation & Header */}
      <div className="space-y-6">
        <Link href="/kb" className="inline-flex items-center gap-2 text-xs text-slate-500 hover:text-blue-400 transition-colors">
          <ChevronLeft className="w-3 h-3" /> Back to Knowledge Base
        </Link>
        
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <span className="px-2 py-0.5 bg-blue-600/10 border border-blue-500/20 rounded text-[10px] font-mono text-blue-400 uppercase tracking-widest">
                {meta.slug || slug}
              </span>
              <div className={clsx("w-2 h-2 rounded-full shadow-[0_0_8px_currentColor]", {
                  "text-red-500": meta.severity === "critical",
                  "text-orange-500": meta.severity === "high",
                  "text-amber-500": meta.severity === "warning",
                  "text-blue-500": meta.severity === "info",
                  "text-slate-500": meta.severity === "low",
              })} />
            </div>
            <h1 className="text-3xl font-bold text-white tracking-tight">
              {meta.title || slug}
            </h1>
          </div>

          <div className="flex flex-wrap gap-2">
            {(meta.environments_seen || []).map((env: string) => (
              <EnvBadge key={env} env={env} />
            ))}
            {meta.theme && (
              <span className="px-3 py-1 bg-slate-800 border border-slate-700 rounded-full text-[10px] font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                <Layers className="w-3 h-3 text-slate-500" />
                {meta.theme}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Metadata Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6 p-8 bg-slate-900/60 border border-slate-800 rounded-[2.5rem] shadow-xl backdrop-blur-md relative overflow-hidden">
        <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500/5 blur-[100px] -z-10" />
        <MetaItem 
          label="Occurrences" 
          value={meta.occurrences || "1"} 
          icon={Activity} 
          valueClassName="text-white"
        />
        <MetaItem 
          label="Severity" 
          value={meta.severity || "info"} 
          icon={AlertTriangle} 
          valueClassName={clsx("px-3 py-0.5 rounded-full inline-block text-[10px] font-black border tracking-tighter shadow-lg", {
            "bg-red-500 text-white border-red-400 shadow-red-500/40": meta.severity === "critical",
            "bg-orange-500 text-white border-orange-400 shadow-orange-500/40": meta.severity === "high",
            "bg-amber-500 text-black border-amber-400 shadow-amber-500/40": meta.severity === "warning",
            "bg-blue-600 text-white border-blue-500 shadow-blue-500/40": meta.severity === "info",
            "bg-slate-700 text-slate-300 border-slate-600": meta.severity === "low",
          })}
        />
        <MetaItem 
          label="First Seen" 
          value={meta.first_seen ? new Date(meta.first_seen).toLocaleDateString() : "Unknown"} 
          icon={Calendar} 
          valueClassName="text-slate-300"
        />
        <MetaItem 
          label="Last Seen" 
          value={meta.last_seen ? new Date(meta.last_seen).toLocaleDateString() : "Unknown"} 
          icon={Calendar} 
          valueClassName="text-slate-300"
        />
      </div>

      {/* Tags */}
      {meta.tags && meta.tags.length > 0 && (
        <div className="flex flex-wrap gap-2 px-2">
          {meta.tags.map((tag: string) => (
            <span key={tag} className="inline-flex items-center gap-1.5 px-3 py-1 bg-slate-900 border border-slate-800 rounded-full text-[10px] font-bold text-slate-400 hover:text-blue-400 hover:border-blue-500/30 transition-all cursor-default shadow-sm group/tag">
              <Tag className="w-3 h-3 opacity-50 group-hover/tag:text-blue-400 transition-colors" />
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Content */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-[2.5rem] p-10 shadow-2xl backdrop-blur-sm min-h-[600px] relative">
         <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-blue-500/20 to-transparent" />
        <AuditViewer markdown={content} />
      </div>

      {/* Related Missions */}
      {meta.related_missions && meta.related_missions.length > 0 && (
        <div className="space-y-6">
          <h2 className="text-xs font-black text-slate-500 uppercase tracking-[0.2em] px-2 flex items-center gap-3">
            <span className="w-10 h-[1px] bg-slate-800" />
            Related Missions
          </h2>
          <div className="flex flex-wrap gap-3">
            {meta.related_missions.map((m: string) => (
              <Link
                key={m}
                href={`/missions/${m}`}
                className="px-5 py-2.5 bg-slate-900/80 border border-slate-800 rounded-2xl text-xs font-mono text-blue-400 hover:bg-blue-500/5 hover:border-blue-500/30 transition-all shadow-lg hover:scale-105 active:scale-95"
              >
                {m}
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MetaItem({ label, value, icon: Icon, valueClassName }: any) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-[10px] font-black text-slate-500 uppercase tracking-[0.15em]">
        <Icon className="w-3 h-3 opacity-50" />
        {label}
      </div>
      <div className={clsx("text-sm font-bold tracking-tight uppercase", valueClassName)}>
        {value}
      </div>
    </div>
  );
}
