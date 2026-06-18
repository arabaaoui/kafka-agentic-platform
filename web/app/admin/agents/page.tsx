"use client";

import { useQuery } from "@tanstack/react-query";
import { getAgentsCatalog, type AgentCard } from "@/lib/api";
import { Bot } from "lucide-react";

function AgentCardComponent({ agent }: { agent: AgentCard }) {
  return (
    <div
      className="rounded-xl border p-5 flex flex-col gap-3"
      style={{
        borderColor: "var(--mrcl-persistent-border-default)",
        backgroundColor: "var(--mrcl-persistent-background-subtle)",
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg" style={{ backgroundColor: "var(--mrcl-persistent-background-default)" }}>
            <Bot className="w-4 h-4" style={{ color: "var(--crf-blue, #003087)" }} />
          </div>
          <h3 className="font-semibold text-sm" style={{ color: "var(--mrcl-persistent-content-default)" }}>
            {agent.name}
          </h3>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <mrcl-tag variant="success">Actif</mrcl-tag>
          <span className="text-xs" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
            v{agent.version}
          </span>
        </div>
      </div>
      <p className="text-sm" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
        {agent.description}
      </p>
      {agent.description_long && (
        <div
          className="text-xs rounded-lg p-3 font-mono leading-relaxed"
          style={{
            backgroundColor: "var(--mrcl-persistent-background-default)",
            color: "var(--mrcl-persistent-content-subtle)",
          }}
        >
          {agent.description_long.slice(0, 200)}
          {agent.description_long.length > 200 ? "…" : ""}
        </div>
      )}
      <div className="text-xs" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
        Dossier : <span className="font-mono">{agent.agent_dir}</span>
      </div>
    </div>
  );
}

export default function AgentsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["agents"],
    queryFn: getAgentsCatalog,
    staleTime: 60_000,
  });

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold text-white tracking-tight">Catalogue des agents</h1>
        <p className="text-slate-500 text-sm mt-1">
          Agents IA actifs de la plateforme — source : <span className="font-mono">agents/*/SKILL.md</span>
        </p>
      </header>

      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div
              key={i}
              className="rounded-xl border h-40 animate-pulse"
              style={{
                borderColor: "var(--mrcl-persistent-border-default)",
                backgroundColor: "var(--mrcl-persistent-background-subtle)",
              }}
            />
          ))}
        </div>
      )}

      {error && (
        <div className="p-4 rounded-lg text-sm" style={{ color: "var(--mrcl-persistent-content-subtle)" }}>
          Impossible de charger le catalogue des agents.
        </div>
      )}

      {data && (
        <>
          <div className="flex items-center gap-2">
            <mrcl-tag variant="info">{data.length} agent{data.length > 1 ? "s" : ""}</mrcl-tag>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {data.map((agent) => (
              <AgentCardComponent key={agent.agent_dir} agent={agent} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
