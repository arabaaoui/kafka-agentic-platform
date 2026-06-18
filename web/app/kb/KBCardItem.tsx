"use client";

import Link from "next/link";
import { Trash2, ChevronRight, FileText } from "lucide-react";
import { useState } from "react";
import { deleteKBCard } from "@/lib/api";
import { DeleteConfirmModal } from "@/components/DeleteConfirmModal";
import { useRouter } from "next/navigation";
import clsx from "clsx";

export function KBCardItem({ card }: { card: any }) {
  const [showDelete, setShowDelete] = useState(false);
  const router = useRouter();

  const handleDelete = async () => {
    await deleteKBCard(card.slug);
    router.refresh(); // Refresh current page to update list
  };

  return (
    <>
      <div
        className="group relative bg-slate-900/40 border border-slate-800 rounded-2xl p-5 hover:bg-slate-900 transition-all hover:scale-[1.02] hover:border-slate-700 shadow-sm flex flex-col justify-between h-full"
      >
        <Link
          href={`/kb/${encodeURIComponent(card.slug)}`}
          className="absolute inset-0 z-0"
        />
        
        <div className="space-y-3 relative z-10 pointer-events-none">
          <div className="flex items-center justify-between">
            <div className={clsx("w-2 h-2 rounded-full shadow-[0_0_8px_currentColor]", {
              "text-red-500": card.severity === "critical",
              "text-orange-500": card.severity === "high",
              "text-amber-500": card.severity === "warning",
              "text-blue-500": card.severity === "info",
              "text-slate-500": card.severity === "low",
            })} />
            <span className="text-[10px] font-mono text-slate-600 group-hover:text-slate-400 transition-colors uppercase">
              {card.slug}
            </span>
          </div>
          <h3 className="text-sm font-bold text-slate-200 group-hover:text-white transition-colors leading-snug">
            {card.title}
          </h3>
        </div>

        <div className="flex items-center justify-between mt-6 pt-4 border-t border-slate-800/50 relative z-10">
          <div className="flex items-center gap-2">
            <FileText className="w-3 h-3 text-slate-600" />
            <span className="text-[10px] font-bold text-slate-500">
              {card.occurrences} {card.occurrences > 1 ? 'occurrences' : 'occurrence'}
            </span>
          </div>
          <div className="flex items-center gap-3">
             <button 
               onClick={() => setShowDelete(true)}
               className="p-1.5 text-slate-700 hover:text-red-400 transition-colors"
               title="Delete Card"
             >
               <Trash2 className="w-3.5 h-3.5" />
             </button>
             <ChevronRight className="w-4 h-4 text-slate-600 group-hover:text-blue-400 group-hover:translate-x-1 transition-all" />
          </div>
        </div>
      </div>

      <DeleteConfirmModal 
        isOpen={showDelete}
        onClose={() => setShowDelete(false)}
        onConfirm={handleDelete}
        title="Delete KB Card"
        description="Are you sure you want to remove this knowledge base card? It will be physically deleted from the repository and removed from the index."
        resourceId={card.slug}
      />
    </>
  );
}
