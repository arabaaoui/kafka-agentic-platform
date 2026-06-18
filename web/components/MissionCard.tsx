import Link from "next/link";
import { EnvBadge } from "./EnvBadge";
import { StatusBadge } from "./StatusBadge";

interface MissionCardProps {
  mission_id: string;
  env: string;
  status: string;
  type: string;
  subject: string;
  tenant: string;
  created_at: string;
  closed_at?: string | null;
}

export function MissionCard({
  mission_id,
  env,
  status,
  type,
  subject,
  tenant,
  created_at,
  closed_at,
}: MissionCardProps) {
  const ts = new Date(created_at).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <Link
      href={`/missions/${encodeURIComponent(mission_id)}`}
      className="block border border-gray-700 rounded-lg p-4 hover:border-gray-500 hover:bg-gray-800/40 transition-colors"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <EnvBadge env={env} />
            <StatusBadge status={status} />
            <span className="text-xs text-gray-500 uppercase tracking-wide">{type}</span>
          </div>
          <p className="text-sm font-mono text-gray-200 truncate">{mission_id}</p>
          <p className="text-xs text-gray-400 mt-0.5">
            <span className="font-medium text-gray-300">{subject}</span>
            {" · "}
            <span className="text-gray-500">{tenant}</span>
          </p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-xs text-gray-500">{ts}</p>
          {closed_at && (
            <p className="text-xs text-gray-600 mt-0.5">
              closed {new Date(closed_at).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
            </p>
          )}
        </div>
      </div>
    </Link>
  );
}
