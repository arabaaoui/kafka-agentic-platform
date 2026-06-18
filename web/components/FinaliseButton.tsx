"use client";

import { useState } from "react";
import { finalizeMission } from "@/lib/api";
import { BookOpen } from "lucide-react";
import Link from "next/link";

interface Props {
  missionId: string;
  alreadyFinalized: boolean;
  kbCardSlug?: string | null;
}

interface FinalizeResult {
  brief_path: string;
  kb_card_slug: string | null;
  kb_card_action: "created" | "updated" | "skipped" | "error";
  kb_index_card_count: number;
  finalized_at: string;
}

export function FinaliseButton({ missionId, alreadyFinalized, kbCardSlug }: Props) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<FinalizeResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (alreadyFinalized && !result) {
    return (
      <div className="text-xs space-y-2 bg-blue-900/10 border border-blue-800/30 rounded-xl p-4">
        <p className="text-blue-400 font-bold flex items-center gap-2">
          <BookOpen className="w-3.5 h-3.5" />
          Mission Capitalized
        </p>
        <p className="text-slate-500 leading-relaxed">
          Knowledge card: <br/>
          {kbCardSlug ? (
            <Link href={`/kb/${encodeURIComponent(kbCardSlug)}`} className="text-blue-300 font-mono hover:underline decoration-blue-500/50 underline-offset-2">
              {kbCardSlug}
            </Link>
          ) : (
             <Link href="/kb" className="text-blue-300 hover:underline">See Knowledge Base</Link>
          )}
        </p>
      </div>
    );
  }

  if (result) {
    return (
      <div className="text-xs space-y-1 bg-green-900/20 border border-green-800 rounded p-3">
        <p className="text-green-400 font-medium">✓ Mission capitalisée</p>
        <p className="text-gray-400">
          BRIEF généré : <code className="text-gray-300">{result.brief_path}</code>
        </p>
        {result.kb_card_slug && (
          <p className="text-gray-400">
            Carte KB{" "}
            <span className="text-amber-300 font-mono">{result.kb_card_slug}</span>{" "}
            <span className="text-gray-500">({result.kb_card_action})</span>
          </p>
        )}
        <p className="text-gray-500">
          Index : {result.kb_index_card_count} cartes · {new Date(result.finalized_at).toLocaleString("fr-FR")}
        </p>
      </div>
    );
  }

  async function handleFinalize() {
    setLoading(true);
    setError(null);
    try {
      const data = await finalizeMission(missionId);
      setResult(data);
    } catch (err: any) {
      // If 409, it means it's already finalized (maybe by another user or a previous attempt)
      if (err.message?.includes("409")) {
        // We set a mock result to trigger the "Already Finalized" view
        // In a real case, we could re-fetch the mission detail
        window.location.reload(); 
        return;
      }
      setError(err instanceof Error ? err.message : "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-500">
        Génère un BRIEF de mission et crée/met à jour la carte Knowledge Base correspondante.
      </p>
      {error && (
        <p className="text-xs text-red-400">Erreur : {error}</p>
      )}
      <button
        onClick={handleFinalize}
        disabled={loading}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded border border-amber-700 text-amber-300 hover:bg-amber-900/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? (
          <>
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            Capitalisation en cours…
          </>
        ) : (
          "📚 Capitaliser cette mission"
        )}
      </button>
    </div>
  );
}
