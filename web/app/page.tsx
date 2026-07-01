import { Metadata } from "next";
import { 
  Activity, 
  Clock, 
  ShieldCheck, 
  Server, 
  Network, 
  Database,
  ArrowUpRight
} from "lucide-react";
import clsx from "clsx";

export const metadata: Metadata = {
  title: "Dashboard | Kafka Agentic",
  description: "Incident auto-triage OS for Kafka InfraOps",
};

export default function DashboardPage() {
  return (
    <div className="space-y-10">
      <header className="flex justify-between items-start">
        <div>
          <h1 className="text-white tracking-tight mrcl-title-l">Agentic Lab</h1>
          <p className="text-slate-400 mt-1 max-w-lg mrcl-body-m-regular">
            Enterprise InfraOps autonomous investigation and diagnostic platform for Kafka ecosystems.
          </p>
        </div>
        <div className="flex gap-2">
          <mrcl-badge variant="info">Production v0.1.0</mrcl-badge>
        </div>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <StatCard 
          title="Active Missions" 
          value="--" 
          icon={Activity}
          color="blue" 
          description="Ongoing investigations"
        />
        <StatCard 
          title="Diagnostic SLA" 
          value="< 1m" 
          icon={Clock}
          color="emerald" 
          description="Average time to triage"
        />
        <StatCard 
          title="Security Audit" 
          value="Pass" 
          icon={ShieldCheck}
          color="amber" 
          description="Global compliance check"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="bg-slate-900/50 border border-slate-800 rounded-3xl p-8 shadow-sm">
          <div className="flex items-center justify-between mb-8">
            <h2 className="text-white mrcl-title-s">System Health</h2>
            <mrcl-tag variant="success">All nominal</mrcl-tag>
          </div>
          <div className="grid grid-cols-1 gap-4">
            <StatusItem label="Backend API" status="Online" icon={Database} />
            <StatusItem label="Worker Pipeline" status="Active" icon={Activity} />
            <StatusItem label="Prometheus Collector" status="Connected" icon={Network} />
            <StatusItem label="Cluster Manager" status="Standby" icon={Server} />
          </div>
        </div>

        <div className="bg-gradient-to-br from-blue-600 to-blue-800 rounded-3xl p-8 text-white relative overflow-hidden group">
          <div className="relative z-10 h-full flex flex-col">
            <h2 className="mb-2 mrcl-title-s">Autonomous Operations</h2>
            <p className="text-blue-100/80 mb-8 max-w-xs mrcl-body-m-regular">
              Monitor, triage, and remediate Kafka incidents automatically with zero-touch diagnostics.
            </p>
            <mrcl-button icon="external-link" href="/missions" className="w-fit">
              Launch Mission
            </mrcl-button>
          </div>
          <Zap className="absolute -bottom-10 -right-10 w-64 h-64 text-white/10 rotate-12 group-hover:rotate-0 transition-transform duration-500" />
        </div>
      </div>
    </div>
  );
}

function StatCard({ title, value, icon: Icon, color, description }: any) {
  const colorMap: any = {
    blue: "text-blue-400 bg-blue-500/5 border-blue-500/20 shadow-blue-500/5",
    emerald: "text-emerald-400 bg-emerald-500/5 border-emerald-500/20 shadow-emerald-500/5",
    amber: "text-amber-400 bg-amber-500/5 border-amber-500/20 shadow-amber-500/5",
  };
  
  return (
    <div className={clsx("p-8 rounded-3xl border transition-all hover:scale-[1.02]", colorMap[color])}>
      <div className="flex justify-between items-start mb-4">
        <div className={clsx("p-2 rounded-xl", {
          "bg-blue-500/10": color === "blue",
          "bg-emerald-500/10": color === "emerald",
          "bg-amber-500/10": color === "amber",
        })}>
          <Icon className="w-5 h-5" />
        </div>
        <span className="tracking-tight mrcl-title-l">{value}</span>
      </div>
      <h3 className="text-slate-400 mb-1 mrcl-body-s-bold uppercase tracking-widest">{title}</h3>
      <p className="text-slate-500 mrcl-body-xs-regular">{description}</p>
    </div>
  );
}

function StatusItem({ label, status, icon: Icon }: { label: string; status: string; icon: any }) {
  return (
    <div className="flex items-center justify-between p-4 bg-slate-800/20 rounded-2xl border border-slate-700/30 hover:bg-slate-800/40 transition-colors">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-slate-900 rounded-lg">
          <Icon className="w-4 h-4 text-slate-400" />
        </div>
        <span className="text-slate-200 mrcl-body-m-regular">{label}</span>
      </div>
      <div className="flex items-center gap-2">
        <mrcl-tag variant="success">{status}</mrcl-tag>
      </div>
    </div>
  );
}

function Zap({ className }: { className?: string }) {
  return (
    <svg 
      viewBox="0 0 24 24" 
      fill="none" 
      stroke="currentColor" 
      strokeWidth="2" 
      strokeLinecap="round" 
      strokeLinejoin="round" 
      className={className}
    >
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" fill="currentColor" />
    </svg>
  );
}
