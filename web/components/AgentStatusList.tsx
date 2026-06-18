import clsx from "clsx";
import type { AgentOutputSummary } from "@/lib/api";

const AGENT_LABELS: Record<string, string> = {
  kafka_strimzi_expert: "Kafka/Strimzi",
  k8s_gcp_sre: "K8s GCP SRE",
  prom_alerts_triage: "Prom Triage",
  evidence_consolidator: "Consolidator",
};

interface Props {
  outputs: AgentOutputSummary[];
  missionStatus: string;
}

const EXPECTED = ["kafka_strimzi_expert", "k8s_gcp_sre", "prom_alerts_triage"];

export function AgentStatusList({ outputs, missionStatus }: Props) {
  const done = new Set(outputs.map((o) => o.agent));
  const isFinished = missionStatus === "CLOSED" || missionStatus === "PARTIAL";
  const isRunning = missionStatus === "OPEN";

  return (
    <div className="grid grid-cols-1 gap-3">
      {EXPECTED.map((agent) => {
        const isDone = done.has(agent);
        const hasFailed = isFinished && !isDone;
        
        return (
          <div
            key={agent}
            className={clsx(
              "flex items-center justify-between p-3 rounded-xl border transition-all",
              isDone
                ? "bg-emerald-500/5 border-emerald-500/20 text-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.02)]"
                : hasFailed
                ? "bg-red-500/5 border-red-500/20 text-red-400"
                : isRunning
                ? "bg-blue-500/5 border-blue-500/20 text-blue-400"
                : "bg-slate-900/50 border-slate-800 text-slate-500",
            )}
          >
            <div className="flex items-center gap-3">
               <div className={clsx(
                "w-2 h-2 rounded-full",
                isDone ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" : 
                hasFailed ? "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]" :
                isRunning ? "bg-blue-500 animate-pulse shadow-[0_0_8px_rgba(59,130,246,0.5)]" : 
                "bg-slate-700",
              )} />
               <span className="text-xs font-bold uppercase tracking-wide">
                 {AGENT_LABELS[agent] ?? agent}
               </span>
            </div>
            <span className="text-[9px] font-black uppercase tracking-widest opacity-60">
               {isDone ? "Completed" : hasFailed ? "Failed" : isRunning ? "Running" : "Pending"}
            </span>
          </div>
        );
      })}
    </div>
  );
}
