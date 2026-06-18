"use client";

import { useQuery } from "@tanstack/react-query";
import { getHealthz, type HealthStatus } from "@/lib/api";
import { getHealthStatus } from "./OpsStrip";
import Link from "next/link";

function buildMessage(data: HealthStatus): { title: string; details: string[] } {
  const details: string[] = [];

  if (data.dead_count >= 1) {
    details.push(`${data.dead_count} déclencheur${data.dead_count > 1 ? "s" : ""} en échec terminal`);
  }
  if ((data.oldest_pending_age_seconds ?? 0) > 600) {
    const minutes = Math.round((data.oldest_pending_age_seconds ?? 0) / 60);
    details.push(`Déclencheur en attente depuis ${minutes} min`);
  }
  if ((data.queue_depth ?? 0) > 50) {
    details.push(`File surchargée : ${data.queue_depth} éléments`);
  }

  const title = details.length > 1 ? "Plusieurs anomalies détectées" : "Anomalie détectée";
  return { title, details };
}

export function AttentionCard() {
  const { data } = useQuery({
    queryKey: ["healthz"],
    queryFn: getHealthz,
    refetchInterval: 5_000,
    staleTime: 2_000,
  });

  const status = getHealthStatus(data);

  if (!data || status === "ok") return null;

  const { title, details } = buildMessage(data);
  const isCritique = status === "critique";

  return (
    <div
      className="mx-6 mt-4 mb-0 rounded-lg border px-5 py-4"
      style={{
        borderColor: isCritique ? "var(--mrcl-persistent-feedback-critical-border, #dc2626)" : "var(--mrcl-persistent-feedback-warning-border, #f59e0b)",
        backgroundColor: isCritique ? "var(--mrcl-persistent-feedback-critical-background, #fef2f2)" : "var(--mrcl-persistent-feedback-warning-background, #fffbeb)",
      }}
    >
      <div className="flex items-start gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <mrcl-tag variant={isCritique ? "error" : "warning"}>{isCritique ? "Critique" : "Attention"}</mrcl-tag>
            <span className="font-semibold text-sm" style={{ color: "var(--mrcl-persistent-content-default)" }}>
              {title}
            </span>
          </div>
          <ul className="text-sm space-y-0.5" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
            {details.map((d) => (
              <li key={d}>• {d}</li>
            ))}
          </ul>
        </div>
        <Link
          href="/missions?view=kanban"
          className="shrink-0 text-sm font-medium underline"
          style={{ color: "var(--crf-blue, #003087)" }}
        >
          Voir les missions →
        </Link>
      </div>
    </div>
  );
}
