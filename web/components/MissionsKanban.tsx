"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getMissionsKanban, retryTrigger, type KanbanMission } from "@/lib/api";
import { KanbanTriggerCard } from "./KanbanTriggerCard";
import Link from "next/link";

interface ColumnHeaderProps {
  label: string;
  count: number;
  variant: string;
}

function ColumnHeader({ label, count, variant }: ColumnHeaderProps) {
  return (
    <div className="flex items-center justify-between mb-3">
      <div className="flex items-center gap-2">
        <mrcl-tag variant={variant}>{label}</mrcl-tag>
      </div>
      <span className="text-xs font-semibold" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
        {count}
      </span>
    </div>
  );
}

const MISSION_STATUS_LABELS: Record<string, string> = {
  CLOSED: "Clôturée",
  PARTIAL: "Partielle",
  OPEN: "En cours",
};

const MISSION_STATUS_VARIANTS: Record<string, string> = {
  CLOSED: "success",
  PARTIAL: "warning",
  OPEN: "info",
};

function MissionCard({ item }: { item: KanbanMission }) {
  const statusLabel = MISSION_STATUS_LABELS[item.status] ?? item.status;
  const statusVariant = MISSION_STATUS_VARIANTS[item.status] ?? "neutral";

  return (
    <Link href={`/missions/${encodeURIComponent(item.mission_id)}`}>
      <div
        className="rounded-lg border p-3 text-sm space-y-2 hover:border-opacity-80 transition-colors cursor-pointer"
        style={{
          borderColor: "var(--mrcl-persistent-border-default)",
          backgroundColor: "var(--mrcl-persistent-background-default)",
        }}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="font-medium truncate flex-1" style={{ color: "var(--mrcl-persistent-content-default)" }}>
            {item.subject}
          </div>
          <mrcl-tag variant={statusVariant}>{statusLabel}</mrcl-tag>
        </div>
        <div className="flex items-center gap-2 text-xs" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
          <span className="truncate max-w-[120px]">{item.mission_id}</span>
          <span>·</span>
          <span>{item.env}</span>
          <span>·</span>
          <span>{item.tenant}</span>
        </div>
      </div>
    </Link>
  );
}

export function MissionsKanban() {
  const queryClient = useQueryClient();
  const [retryingIds, setRetryingIds] = useState<Set<string>>(new Set());

  const { data, isLoading, error } = useQuery({
    queryKey: ["kanban"],
    queryFn: getMissionsKanban,
    refetchInterval: 8_000,
    staleTime: 3_000,
  });

  const retryMutation = useMutation({
    mutationFn: retryTrigger,
    onMutate: (id) => setRetryingIds((s) => new Set(s).add(id)),
    onSettled: (_, __, id) => {
      setRetryingIds((s) => { const n = new Set(s); n.delete(id); return n; });
      queryClient.invalidateQueries({ queryKey: ["kanban"] });
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-40" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
        Chargement du Kanban…
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-4 text-sm" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
        Impossible de charger le Kanban.
      </div>
    );
  }

  const columns = [
    { key: "en_attente" as const, label: "En attente", variant: "info", items: data.en_attente },
    { key: "reservee" as const, label: "Réservée", variant: "warning", items: data.reservee },
    { key: "terminee" as const, label: "Terminée", variant: "success", items: data.terminee },
    { key: "en_echec" as const, label: "En échec", variant: "error", items: data.en_echec },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-2">
      {columns.map(({ key, label, variant, items }) => (
        <div
          key={key}
          className="rounded-xl border p-4 min-h-[300px]"
          style={{
            borderColor: "var(--mrcl-persistent-border-default)",
            backgroundColor: "var(--mrcl-persistent-background-subtle)",
          }}
        >
          <ColumnHeader label={label} count={items.length} variant={variant} />
          <div className="space-y-2">
            {items.length === 0 && (
              <div className="text-xs py-4 text-center" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
                Aucun élément
              </div>
            )}
            {key === "terminee"
              ? (items as KanbanMission[]).map((m) => (
                  <MissionCard key={m.mission_id} item={m} />
                ))
              : (items as Parameters<typeof KanbanTriggerCard>[0]["item"][]).map((t) => (
                  <KanbanTriggerCard
                    key={t.id}
                    item={t}
                    column={key}
                    onRetry={key === "en_echec" ? (id) => retryMutation.mutate(id) : undefined}
                    isRetrying={retryingIds.has(t.id)}
                  />
                ))}
          </div>
        </div>
      ))}
    </div>
  );
}
