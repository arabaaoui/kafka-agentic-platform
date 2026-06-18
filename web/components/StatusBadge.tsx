import clsx from "clsx";

type Status = "OPEN" | "CLOSED" | "PARTIAL" | string;

const COLOR: Record<string, string> = {
  OPEN:    "bg-blue-500/10 text-blue-400 border-blue-500/20",
  CLOSED:  "bg-slate-500/10 text-slate-400 border-slate-500/20",
  PARTIAL: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  RUNNING: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
};

export function StatusBadge({ status }: { status: Status }) {
  const s = status.toUpperCase();
  return (
    <span
      className={clsx(
        "inline-flex items-center px-2.5 py-0.5 rounded-full border text-[10px] font-bold uppercase tracking-wider",
        COLOR[s] ?? "bg-slate-800 text-slate-400 border-slate-700",
      )}
    >
      <span className={clsx("w-1 h-1 rounded-full mr-1.5", {
        "bg-blue-400": s === "OPEN",
        "bg-slate-400": s === "CLOSED",
        "bg-amber-400": s === "PARTIAL",
        "bg-emerald-400": s === "RUNNING",
      })} />
      {status}
    </span>
  );
}
