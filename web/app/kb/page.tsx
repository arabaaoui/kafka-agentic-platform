import Link from "next/link";
import { BookOpen, FileText, ChevronRight, ChevronLeft } from "lucide-react";
import { KBFilterBar } from "@/components/KBFilterBar";
import { KBCardItem } from "./KBCardItem";
import clsx from "clsx";

export const revalidate = 60;

interface KBCard {
  slug: string;
  title: string;
  theme: string;
  severity: string;
  occurrences: number;
  last_mission: string;
}

interface KBCardListResponse {
  items: KBCard[];
  total: number;
  limit: number;
  offset: number;
}

async function fetchCards(params?: {
  theme?: string;
  limit?: number;
  offset?: number;
}): Promise<KBCardListResponse> {
  try {
    const q = new URLSearchParams();
    if (params?.theme) q.set("theme", params.theme);
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.offset) q.set("offset", String(params.offset));
    
    const res = await fetch(
      `${process.env.API_INTERNAL_URL ?? "http://backend:8000"}/v1/kb/cards?${q}`,
      { cache: "no-store" }
    );
    if (!res.ok) return { items: [], total: 0, limit: 50, offset: 0 };
    return await res.json();
  } catch {
    return { items: [], total: 0, limit: 50, offset: 0 };
  }
}

// Separate fetch for unique themes
async function fetchAllThemes(): Promise<string[]> {
  try {
    const res = await fetch(
      `${process.env.API_INTERNAL_URL ?? "http://backend:8000"}/v1/kb/cards`,
      { cache: "no-store" }
    );
    if (!res.ok) return [];
    const data: KBCardListResponse = await res.json();
    return [...new Set(data.items.map((c) => c.theme).filter(Boolean))].sort();
  } catch {
    return [];
  }
}

export default async function KBPage({
  searchParams,
}: {
  searchParams: { theme?: string; page?: string };
}) {
  const page = Number(searchParams.page) || 1;
  const limit = 100;
  const offset = (page - 1) * limit;

  const [data, allThemes] = await Promise.all([
    fetchCards({ theme: searchParams.theme, limit, offset }),
    fetchAllThemes()
  ]);

  const themes = [...new Set(data.items.map((c) => c.theme).filter(Boolean))].sort();
  const totalPages = Math.ceil(data.total / limit);

  return (
    <div className="space-y-8">
      <header className="flex flex-col md:flex-row md:items-baseline justify-between gap-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            Knowledge Base
            <span className="text-slate-500 font-normal text-sm bg-slate-900 px-2 py-0.5 rounded-lg border border-slate-800">
              {data.total} cards
            </span>
          </h1>
          <p className="text-slate-500 text-sm mt-1">Autonomous capitalization of incident diagnostics and solutions.</p>
        </div>
        <KBFilterBar themes={allThemes} currentTheme={searchParams.theme} />
      </header>

      {data.items.length === 0 ? (
        <div className="py-24 text-center bg-slate-900/20 border border-slate-800 border-dashed rounded-3xl">
          <BookOpen className="w-8 h-8 text-slate-700 mx-auto mb-4" />
          <p className="text-slate-500 text-sm italic">
            {searchParams.theme ? `No cards found for theme "${searchParams.theme}".` : "No KB cards found. Finalize a mission to capitalize its findings."}
          </p>
        </div>
      ) : (
        <div className="space-y-12">
          {themes.map((theme) => (
            <section key={theme} className="space-y-4">
              <div className="flex items-center gap-3 px-2">
                 <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
                 <h2 className="text-xs font-black text-slate-400 uppercase tracking-widest">
                    {theme}
                 </h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {data.items
                  .filter((c) => c.theme === theme)
                  .map((card) => (
                    <KBCardItem key={card.slug} card={card} />
                  ))}
              </div>
            </section>
          ))}

          {totalPages > 1 && (
             <Pagination page={page} total={totalPages} theme={searchParams.theme} />
          )}
        </div>
      )}
    </div>
  );
}

function Pagination({ page, total, theme }: { page: number; total: number; theme?: string }) {
  const p = (n: number) => {
    const params = new URLSearchParams();
    if (theme) params.set("theme", theme);
    params.set("page", String(n));
    return `/kb?${params.toString()}`;
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
