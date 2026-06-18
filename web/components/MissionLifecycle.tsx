"use client";

import { useQuery } from "@tanstack/react-query";
import { getMissionLifecycle, type MissionLifecycle as LifecycleData } from "@/lib/api";

interface MissionLifecycleProps {
  missionId: string;
}

function formatDate(iso: string | null): string {
  if (!iso) return "--";
  return new Date(iso).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function durationBetween(from: string | null, to: string | null): string | null {
  if (!from || !to) return null;
  const ms = new Date(to).getTime() - new Date(from).getTime();
  if (ms < 0) return null;
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}min ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}min`;
}

interface StepProps {
  label: string;
  timestamp: string | null;
  detail?: string | null;
  duration?: string | null;
  isLast?: boolean;
}

function Step({ label, timestamp, detail, duration, isLast }: StepProps) {
  const active = timestamp !== null;
  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div
          className="w-3 h-3 rounded-full mt-0.5 shrink-0"
          style={{
            backgroundColor: active
              ? "var(--crf-blue, #003087)"
              : "var(--mrcl-persistent-border-default)",
          }}
        />
        {!isLast && (
          <div
            className="w-px flex-1 my-1"
            style={{ backgroundColor: "var(--mrcl-persistent-border-default)" }}
          />
        )}
      </div>
      <div className="pb-4">
        <div className="flex items-center gap-2">
          <span
            className="text-sm font-medium"
            style={{
              color: active
                ? "var(--mrcl-persistent-content-default)"
                : "var(--mrcl-persistent-content-subtle)",
            }}
          >
            {label}
          </span>
          {duration && (
            <span className="text-xs" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
              (+{duration})
            </span>
          )}
        </div>
        <div className="text-xs mt-0.5" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
          {active ? formatDate(timestamp) : "En attente"}
        </div>
        {detail && (
          <div
            className="text-xs mt-1 font-mono"
            style={{ color: "var(--mrcl-persistent-content-subtle)" }}
          >
            {detail}
          </div>
        )}
      </div>
    </div>
  );
}

export function MissionLifecycle({ missionId }: MissionLifecycleProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["lifecycle", missionId],
    queryFn: () => getMissionLifecycle(missionId),
    refetchInterval: (query) => {
      const d = query.state.data as LifecycleData | undefined;
      return d?.mission_status !== "CLOSED" ? 3_000 : false;
    },
  });

  if (isLoading) {
    return (
      <div className="py-4" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
        Chargement du cycle de vie…
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="py-4 text-sm" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
        Cycle de vie non disponible.
      </div>
    );
  }

  const d1 = durationBetween(data.received_at, data.claimed_at);
  const d2 = durationBetween(data.claimed_at, data.mission_created_at);
  const d3 = durationBetween(data.mission_created_at, data.mission_closed_at);

  return (
    <div className="space-y-0">
      {data.attempts > 0 && (
        <div className="mb-3 flex items-center gap-3 text-sm">
          <span style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
            Tentatives :
          </span>
          <span className="font-semibold" style={{ color: "var(--mrcl-persistent-content-default)" }}>
            {data.attempts}
          </span>
          {data.last_error && (
            <span
              className="text-xs font-mono px-2 py-0.5 rounded"
              style={{
                backgroundColor: "var(--mrcl-persistent-feedback-critical-background, #fef2f2)",
                color: "var(--mrcl-persistent-feedback-critical-content, #dc2626)",
              }}
            >
              {data.last_error}
            </span>
          )}
        </div>
      )}
      <Step
        label="Reçu"
        timestamp={data.received_at}
      />
      <Step
        label="Réservé"
        timestamp={data.claimed_at}
        detail={data.claimed_by ? `Worker : ${data.claimed_by}` : null}
        duration={d1 ?? undefined}
      />
      <Step
        label="Mission créée"
        timestamp={data.mission_created_at}
        duration={d2 ?? undefined}
      />
      <Step
        label="Traité"
        timestamp={data.mission_closed_at}
        detail={data.mission_status !== "CLOSED" ? "En cours…" : null}
        duration={d3 ?? undefined}
        isLast
      />
    </div>
  );
}
