"use client";

import { useQuery } from "@tanstack/react-query";
import { getHealthz, type HealthStatus } from "@/lib/api";

function formatAge(seconds: number | null): string {
  if (seconds === null) return "--";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}min`;
  return `${Math.round(seconds / 3600)}h`;
}

export function getHealthStatus(data: HealthStatus | undefined): "ok" | "attention" | "critique" {
  if (!data) return "ok";
  if (data.dead_count >= 1 || (data.oldest_pending_age_seconds ?? 0) > 600) return "critique";
  if ((data.queue_depth ?? 0) > 50) return "attention";
  return "ok";
}

export function OpsStrip() {
  const { data, isLoading } = useQuery({
    queryKey: ["healthz"],
    queryFn: getHealthz,
    refetchInterval: 5_000,
    staleTime: 2_000,
  });

  const status = getHealthStatus(data);

  const badgeVariant = status === "critique" ? "error" : status === "attention" ? "warning" : "success";
  const badgeLabel = status === "critique" ? "Critique" : status === "attention" ? "Attention" : "Opérationnel";

  if (isLoading) {
    return (
      <div
        className="flex items-center gap-4 px-6 py-2 border-b text-sm"
        style={{ borderColor: "var(--mrcl-persistent-border-default)", backgroundColor: "var(--mrcl-persistent-background-subtle)" }}
      >
        <span style={{ color: "var(--mrcl-persistent-content-subtle)" }}>Chargement…</span>
      </div>
    );
  }

  return (
    <div
      className="flex items-center gap-6 px-6 py-2 border-b text-sm flex-wrap"
      style={{ borderColor: "var(--mrcl-persistent-border-default)", backgroundColor: "var(--mrcl-persistent-background-subtle)" }}
    >
      <div className="flex items-center gap-2">
        <span style={{ color: "var(--mrcl-persistent-content-subtle)" }}>Workers</span>
        <span className="font-semibold" style={{ color: "var(--mrcl-persistent-content-default)" }}>
          {data?.worker_count ?? "--"}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span style={{ color: "var(--mrcl-persistent-content-subtle)" }}>File</span>
        <span className="font-semibold" style={{ color: "var(--mrcl-persistent-content-default)" }}>
          {data?.queue_depth ?? "--"}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span style={{ color: "var(--mrcl-persistent-content-subtle)" }}>En attente</span>
        <span className="font-semibold" style={{ color: "var(--mrcl-persistent-content-default)" }}>
          {formatAge(data?.oldest_pending_age_seconds ?? null)}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span style={{ color: "var(--mrcl-persistent-content-subtle)" }}>En échec</span>
        <span className="font-semibold" style={{ color: "var(--mrcl-persistent-content-default)" }}>
          {data?.dead_count ?? "--"}
        </span>
      </div>
      <div className="ml-auto">
        <mrcl-tag variant={badgeVariant}>{badgeLabel}</mrcl-tag>
      </div>
    </div>
  );
}
