"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getSkillsCatalog, type SkillCard } from "@/lib/api";
import { Layers } from "lucide-react";

const CATEGORY_LABELS: Record<string, string> = {
  infrastructure: "Infrastructure",
  données: "Données",
  externe: "Externe",
  autre: "Autre",
};

const CATEGORY_VARIANTS: Record<string, string> = {
  infrastructure: "warning",
  données: "info",
  externe: "success",
  autre: "neutral",
};

function SkillCardComponent({ card }: { card: SkillCard }) {
  return (
    <div
      className="rounded-xl border p-4 space-y-3"
      style={{
        borderColor: "var(--mrcl-persistent-border-default)",
        backgroundColor: "var(--mrcl-persistent-background-subtle)",
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-semibold text-sm" style={{ color: "var(--mrcl-persistent-content-default)" }}>
            {card.agent_name}
          </div>
          <div className="text-xs font-mono mt-0.5" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
            {card.agent_dir}
          </div>
        </div>
        <mrcl-tag variant={CATEGORY_VARIANTS[card.category] ?? "neutral"}>
          {CATEGORY_LABELS[card.category] ?? card.category}
        </mrcl-tag>
      </div>
      {card.skills.length > 0 && (
        <ul className="space-y-1">
          {card.skills.map((skill, i) => (
            <li key={i} className="flex items-start gap-1.5 text-xs" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
              <span className="mt-0.5 shrink-0" style={{ color: "var(--crf-blue, #003087)" }}>•</span>
              <span>{skill}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function SkillsPage() {
  const [category, setCategory] = useState<string>("toutes");

  const { data, isLoading, error } = useQuery({
    queryKey: ["skills"],
    queryFn: getSkillsCatalog,
    staleTime: 60_000,
  });

  const categories = ["toutes", "infrastructure", "données", "externe", "autre"];

  const filtered = data
    ? category === "toutes"
      ? data
      : data.filter((c) => c.category === category)
    : [];

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold text-white tracking-tight">Catalogue des compétences</h1>
        <p className="text-slate-500 text-sm mt-1">
          Capacités disponibles par agent — filtrables par catégorie.
        </p>
      </header>

      {/* Filtres catégorie */}
      <div className="flex items-center gap-2 flex-wrap">
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() => setCategory(cat)}
            className="px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors"
            style={{
              borderColor: category === cat ? "var(--crf-blue, #003087)" : "var(--mrcl-persistent-border-default)",
              backgroundColor: category === cat ? "var(--crf-blue, #003087)" : "transparent",
              color: category === cat ? "white" : "var(--mrcl-persistent-content-subtle)",
            }}
          >
            {CATEGORY_LABELS[cat] ?? "Toutes"}
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="rounded-xl border h-32 animate-pulse"
              style={{
                borderColor: "var(--mrcl-persistent-border-default)",
                backgroundColor: "var(--mrcl-persistent-background-subtle)",
              }}
            />
          ))}
        </div>
      )}

      {error && (
        <div className="p-4 text-sm" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
          Impossible de charger le catalogue des compétences.
        </div>
      )}

      {data && (
        <>
          <div className="flex items-center gap-2">
            <mrcl-tag variant="info">{filtered.length} agent{filtered.length > 1 ? "s" : ""}</mrcl-tag>
            {category !== "toutes" && (
              <span className="text-xs" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
                — filtrés par « {CATEGORY_LABELS[category] ?? category} »
              </span>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filtered.map((card) => (
              <SkillCardComponent key={card.agent_dir} card={card} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
