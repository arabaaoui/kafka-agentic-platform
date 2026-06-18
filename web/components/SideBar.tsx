"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Target,
  Zap,
  BookOpen,
  Server,
  Filter,
  ChevronRight,
  Shield,
  Sun,
  Moon,
  Activity,
  Bot,
  Layers
} from "lucide-react";
import clsx from "clsx";

const links = [
  { href: "/", label: "Tableau de bord", icon: LayoutDashboard },
  { href: "/missions", label: "Missions", icon: Target },
  { href: "/triggers", label: "Déclencheurs", icon: Zap },
  { href: "/monitoring", label: "Surveillance", icon: Activity },
  { href: "/kb", label: "Base de connaissances", icon: BookOpen },
  { href: "/settings/tenants", label: "Infrastructure", icon: Server },
  { href: "/settings/filters", label: "Filtres", icon: Filter },
  { href: "/admin/audit", label: "Audit admin", icon: Shield },
  { href: "/admin/agents", label: "Agents", icon: Bot },
  { href: "/admin/skills", label: "Compétences", icon: Layers },
];

export function SideBar() {
  const pathname = usePathname();
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const currentMode = document.documentElement.getAttribute("data-mode") as "dark" | "light";
    if (currentMode) {
      setTheme(currentMode);
    }
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    document.documentElement.setAttribute("data-mode", nextTheme);
    if (nextTheme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  };

  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-900/50 flex flex-col h-screen sticky top-0">
      <div className="p-6">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center shadow-lg shadow-blue-500/20">
            <Zap className="w-5 h-5 text-white fill-white" />
          </div>
          <span className="text-white font-bold tracking-tight text-lg mrcl-title-xs">
            Kafka Agentic
          </span>
        </div>
      </div>

      <nav className="flex-1 px-4 space-y-1 mt-4">
        {links.map((l) => {
          const isActive = pathname === l.href || (l.href !== "/" && pathname.startsWith(l.href));
          return (
            <Link
              key={l.href}
              href={l.href}
              className={clsx(
                "flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-all group mrcl-body-m-regular",
                isActive 
                  ? "bg-blue-600/10 text-blue-400 border border-blue-500/20 mrcl-body-m-bold" 
                  : "text-slate-400 hover:text-slate-100 hover:bg-slate-800/50 border border-transparent"
              )}
            >
              <div className="flex items-center gap-3">
                <l.icon className={clsx("w-4 h-4", isActive ? "text-blue-400" : "text-slate-500 group-hover:text-slate-300")} />
                {l.label}
              </div>
              {isActive && <ChevronRight className="w-3 h-3 text-blue-400" />}
            </Link>
          );
        })}
      </nav>

      <div className="p-4 mt-auto border-t border-slate-800/50 space-y-4">
        <div className="bg-slate-800/30 rounded-xl p-4 border border-slate-700/30">
          <p className="text-[10px] uppercase tracking-widest text-slate-500 mb-2 mrcl-body-xs-bold">Thème</p>
          <button
            onClick={toggleTheme}
            className="w-full flex items-center justify-between px-3 py-2 bg-slate-800/50 hover:bg-slate-800 rounded-lg text-xs text-slate-300 transition-colors border border-slate-700/30"
          >
            <div className="flex items-center gap-2">
              {theme === "dark" ? <Moon className="w-3.5 h-3.5" /> : <Sun className="w-3.5 h-3.5" />}
              <span className="capitalize">{theme === "dark" ? "Sombre" : "Clair"}</span>
            </div>
            <span className="text-[10px] text-blue-400 font-bold">Basculer</span>
          </button>
        </div>

        <div className="bg-slate-800/30 rounded-xl p-4 border border-slate-700/30">
          <p className="text-[10px] uppercase tracking-widest text-slate-500 mb-2 mrcl-body-xs-bold">Statut système</p>
          <div className="flex items-center gap-2">
            <mrcl-tag variant="success">Connecté</mrcl-tag>
          </div>
        </div>
      </div>
    </aside>
  );
}
