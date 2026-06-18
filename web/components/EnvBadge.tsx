import clsx from "clsx";

type Env = "PREPROD" | "PROD" | "REC" | "DEV" | "LAB" | string;

const COLOR: Record<string, string> = {
  PROD:    "bg-red-500/10 text-red-400 border-red-500/20",
  PREPROD: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  REC:     "bg-blue-500/10 text-blue-400 border-blue-500/20",
  DEV:     "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  LAB:     "bg-violet-500/10 text-violet-400 border-violet-500/20",
};

const DEFAULT = "bg-slate-800 text-slate-400 border-slate-700";

interface Props {
  env: Env;
  className?: string;
}

export function EnvBadge({ env, className }: Props) {
  const key = env.toUpperCase();
  return (
    <span
      aria-label={`Environment: ${key}`}
      className={clsx(
        "inline-flex items-center px-2 py-0.5 rounded-full border text-[9px] font-black tracking-widest uppercase",
        COLOR[key] ?? DEFAULT,
        className,
      )}
    >
      {key}
    </span>
  );
}
