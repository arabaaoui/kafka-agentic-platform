"use client";

import { useQuery } from "@tanstack/react-query";
import { getMetricsSnapshot } from "@/lib/api";
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from "recharts";

const COLOR_PRIMARY = "#3b82f6";
const COLOR_SECONDARY = "#8b5cf6";
const COLOR_SUCCESS = "#10b981";
const COLOR_ERROR = "#ef4444";
const COLOR_MUTED = "#64748b";

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function ChartSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      className="rounded-xl border p-5"
      style={{
        borderColor: "var(--mrcl-persistent-border-default)",
        backgroundColor: "var(--mrcl-persistent-background-subtle)",
      }}
    >
      <h3 className="text-xs font-black uppercase tracking-widest mb-4" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
        {title}
      </h3>
      {children}
    </div>
  );
}

export function MonitoringCharts() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["metrics"],
    queryFn: getMetricsSnapshot,
    refetchInterval: 10_000,
    staleTime: 5_000,
  });

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="rounded-xl border h-48 animate-pulse"
            style={{
              borderColor: "var(--mrcl-persistent-border-default)",
              backgroundColor: "var(--mrcl-persistent-background-subtle)",
            }}
          />
        ))}
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-4 text-sm" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
        Impossible de charger les métriques de surveillance.
      </div>
    );
  }

  const historyData = data.history.map((p) => ({
    time: formatTime(p.ts),
    "En file": p.depth,
    "En cours": p.inflight,
  }));

  const durationData = [
    { name: "p50", "Durée (s)": data.duration_p50_seconds ?? 0 },
    { name: "p95", "Durée (s)": data.duration_p95_seconds ?? 0 },
    { name: "p99", "Durée (s)": data.duration_p99_seconds ?? 0 },
  ];

  const outcomesData = [
    { name: "Terminées (24h)", value: data.mission_completed_24h },
    { name: "En échec", value: data.mission_dead_total },
  ];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {/* Graphique 1 : évolution file d'attente */}
      <ChartSection title="Profondeur de file · 10 dernières minutes">
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={historyData} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
            <XAxis dataKey="time" tick={{ fontSize: 9, fill: COLOR_MUTED }} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 9, fill: COLOR_MUTED }} allowDecimals={false} />
            <Tooltip
              contentStyle={{ fontSize: 11, backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: 6 }}
              labelStyle={{ color: "#94a3b8" }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line type="monotone" dataKey="En file" stroke={COLOR_PRIMARY} strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="En cours" stroke={COLOR_SECONDARY} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </ChartSection>

      {/* Graphique 2 : latences p50/p95/p99 */}
      <ChartSection title="Latence de traitement · dernière heure">
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={durationData} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
            <XAxis dataKey="name" tick={{ fontSize: 10, fill: COLOR_MUTED }} />
            <YAxis tick={{ fontSize: 9, fill: COLOR_MUTED }} unit="s" />
            <Tooltip
              contentStyle={{ fontSize: 11, backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: 6 }}
              formatter={(v: number) => [`${v.toFixed(1)}s`, "Durée"]}
            />
            <Bar dataKey="Durée (s)" fill={COLOR_PRIMARY} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartSection>

      {/* Graphique 3 : répartition résultats 24h */}
      <ChartSection title="Résultats des missions · 24 dernières heures">
        <ResponsiveContainer width="100%" height={180}>
          <PieChart>
            <Pie
              data={outcomesData}
              cx="50%"
              cy="50%"
              innerRadius={45}
              outerRadius={70}
              paddingAngle={3}
              dataKey="value"
              label={({ name, value }) => `${name}: ${value}`}
              labelLine={false}
            >
              <Cell fill={COLOR_SUCCESS} />
              <Cell fill={COLOR_ERROR} />
            </Pie>
            <Tooltip
              contentStyle={{ fontSize: 11, backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: 6 }}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="flex justify-center gap-4 text-xs mt-1" style={{ color: COLOR_MUTED }}>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: COLOR_SUCCESS }} />
            Terminées : {data.mission_completed_24h}
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: COLOR_ERROR }} />
            En échec : {data.mission_dead_total}
          </span>
        </div>
      </ChartSection>
    </div>
  );
}
