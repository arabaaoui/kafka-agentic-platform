"use client";

import { type KanbanTrigger } from "@/lib/api";

type Column = "en_attente" | "reservee" | "en_echec";

interface KanbanTriggerCardProps {
  item: KanbanTrigger;
  column: Column;
  onRetry?: (triggerId: string) => void;
  isRetrying?: boolean;
}

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "à l'instant";
  if (mins < 60) return `il y a ${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `il y a ${hours}h`;
  return `il y a ${Math.floor(hours / 24)}j`;
}

const SOURCE_LABELS: Record<string, string> = {
  jira: "Jira",
  alertmanager: "Alertmanager",
  care: "Care",
};

export function KanbanTriggerCard({ item, column, onRetry, isRetrying }: KanbanTriggerCardProps) {
  return (
    <div
      className="rounded-lg border p-3 text-sm space-y-1.5"
      style={{
        borderColor: "var(--mrcl-persistent-border-default)",
        backgroundColor: "var(--mrcl-persistent-background-default)",
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-medium truncate" style={{ color: "var(--mrcl-persistent-content-default)" }}>
          {item.external_id}
        </span>
        <span className="shrink-0 text-xs" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
          {SOURCE_LABELS[item.source] ?? item.source}
        </span>
      </div>

      <div className="flex items-center gap-3 text-xs" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
        <span>{item.tenant}</span>
        <span>·</span>
        <span>{formatRelative(item.received_at)}</span>
        {item.attempts > 0 && (
          <>
            <span>·</span>
            <span>{item.attempts} tentative{item.attempts > 1 ? "s" : ""}</span>
          </>
        )}
      </div>

      {column === "reservee" && item.claimed_by && (
        <div className="text-xs truncate" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
          Worker : {item.claimed_by}
        </div>
      )}

      {column === "en_echec" && item.last_error && (
        <div
          className="text-xs font-mono truncate rounded px-1.5 py-0.5"
          style={{
            backgroundColor: "var(--mrcl-persistent-feedback-critical-background, #fef2f2)",
            color: "var(--mrcl-persistent-feedback-critical-content, #dc2626)",
          }}
          title={item.last_error}
        >
          {item.last_error.slice(0, 60)}{item.last_error.length > 60 ? "…" : ""}
        </div>
      )}

      {column === "en_echec" && onRetry && (
        <div className="pt-1">
          <mrcl-button
            onClick={() => !isRetrying && onRetry(item.id)}
            className="text-xs"
          >
            {isRetrying ? "Relance…" : "Relancer"}
          </mrcl-button>
        </div>
      )}
    </div>
  );
}
