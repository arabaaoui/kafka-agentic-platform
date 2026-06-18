"use client";

import { useEffect, useState } from "react";
import {
  getSystemAuditLogs,
  reloadTenants,
  testInfrastructureEnv,
  listInfrastructureTenants,
} from "@/lib/api";
import { Activity, Server, Terminal, CheckCircle, Play } from "lucide-react";
import clsx from "clsx";
import { MonitoringCharts } from "@/components/MonitoringCharts";

export default function MonitoringPage() {
  const [logs, setLogs] = useState<any[]>([]);
  const [tenants, setTenants] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [testingEnv, setTestingEnv] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<any>(null);
  const [reloadMsg, setReloadMsg] = useState<string | null>(null);

  const fetchLogs = async () => {
    try {
      const [auditRes, tenantsRes] = await Promise.all([
        getSystemAuditLogs({ limit: 15 }),
        listInfrastructureTenants(),
      ]);
      setLogs(auditRes.items || []);
      setTenants(tenantsRes || []);
    } catch (err) {
      console.error("Erreur chargement surveillance :", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
    const interval = setInterval(fetchLogs, 10_000);
    return () => clearInterval(interval);
  }, []);

  const handleReload = async () => {
    try {
      const res = await reloadTenants();
      setReloadMsg(`Locataires rechargés : ${res.tenants.join(", ")}`);
      fetchLogs();
      setTimeout(() => setReloadMsg(null), 5000);
    } catch (err: any) {
      setReloadMsg(`Erreur rechargement : ${err.message}`);
      setTimeout(() => setReloadMsg(null), 5000);
    }
  };

  const handleTestEnv = async (tenant: string, slug: string) => {
    setTestingEnv(`${tenant}/${slug}`);
    setTestResult(null);
    try {
      const res = await testInfrastructureEnv(tenant, slug);
      setTestResult(res);
    } catch (err: any) {
      setTestResult({ status: "error", message: err.message });
    } finally {
      setTestingEnv(null);
    }
  };

  return (
    <div className="space-y-8">
      <header className="flex justify-between items-center">
        <div>
          <h1 className="text-white tracking-tight mrcl-title-l">Surveillance</h1>
          <p className="text-slate-400 mt-1 max-w-lg mrcl-body-m-regular">
            Métriques temps réel de la plateforme — profondeur de file, latences et résultats des missions.
          </p>
        </div>
        <div className="flex gap-3">
          <mrcl-button icon="refresh" onClick={fetchLogs}>Actualiser</mrcl-button>
          <mrcl-button icon="plus" onClick={handleReload}>Recharger les locataires</mrcl-button>
        </div>
      </header>

      {reloadMsg && (
        <div className="p-4 bg-blue-600/10 border border-blue-500/20 rounded-xl flex items-center gap-2 text-blue-400 mrcl-body-m-regular animate-fade-in">
          <CheckCircle className="w-5 h-5 shrink-0" />
          <span>{reloadMsg}</span>
        </div>
      )}

      {/* Graphiques temps réel */}
      <MonitoringCharts />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Journal d'activité */}
        <div className="lg:col-span-2 bg-slate-900/50 border border-slate-800 rounded-3xl p-6 flex flex-col h-[550px]">
          <div className="flex items-center gap-3 mb-6">
            <Terminal className="w-5 h-5 text-blue-400" />
            <h2 className="text-white mrcl-title-s">Journal d&apos;activité</h2>
            <mrcl-tag variant="info">Temps réel</mrcl-tag>
          </div>
          <div className="flex-1 overflow-y-auto bg-black/40 rounded-2xl p-4 font-mono text-xs text-slate-300 space-y-3 scrollbar-thin">
            {logs.length === 0 ? (
              <div className="text-slate-500 italic text-center py-20">Aucun événement système enregistré.</div>
            ) : (
              logs.map((logItem) => (
                <div key={logItem.id} className="border-b border-slate-800/40 pb-2 flex flex-col gap-1 hover:bg-slate-800/10 px-2 rounded transition-colors">
                  <div className="flex items-center justify-between text-[10px] text-slate-500">
                    <div className="flex items-center gap-2">
                      <span className="text-blue-400 font-bold">[{logItem.action}]</span>
                      <span className="text-emerald-500">({logItem.resource_type})</span>
                    </div>
                    <span>{new Date(logItem.created_at).toLocaleTimeString("fr-FR")}</span>
                  </div>
                  <p className="text-slate-200 mrcl-body-s-regular">{logItem.resource_id}</p>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Diagnostics environnements */}
        <div className="bg-slate-900/50 border border-slate-800 rounded-3xl p-6 flex flex-col h-[550px] overflow-y-auto">
          <div className="flex items-center gap-3 mb-6">
            <Server className="w-5 h-5 text-blue-400" />
            <h2 className="text-white mrcl-title-s">Diagnostics actifs</h2>
          </div>
          <div className="space-y-4">
            <p className="text-slate-400 mrcl-body-s-regular mb-4">
              Tester l&apos;impersonification GSA et la connectivité GKE :
            </p>
            {tenants.length === 0 ? (
              <div className="text-slate-500 italic text-center py-8">Aucun environnement enregistré.</div>
            ) : (
              tenants.map((t) => (
                <div key={t.tenant} className="bg-slate-800/20 border border-slate-700/30 rounded-2xl p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-white font-bold text-sm mrcl-body-m-bold">{t.display_name}</span>
                    <mrcl-tag variant="info">{t.autonomy_level}</mrcl-tag>
                  </div>
                  <div className="space-y-2">
                    {Object.keys(t.envs).map((envSlug) => {
                      const isTesting = testingEnv === `${t.tenant}/${envSlug}`;
                      return (
                        <div key={envSlug} className="flex items-center justify-between bg-slate-900/40 p-2.5 rounded-xl border border-slate-800/60">
                          <span className="text-slate-300 font-bold uppercase text-xs mrcl-body-xs-bold">{envSlug}</span>
                          <button
                            onClick={() => handleTestEnv(t.tenant, envSlug)}
                            disabled={!!testingEnv}
                            className="flex items-center gap-1 text-[10px] text-blue-400 font-bold hover:text-blue-300 disabled:opacity-50"
                          >
                            <Play className="w-3 h-3 fill-current" />
                            {isTesting ? "Test en cours…" : "Tester"}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))
            )}
            {testResult && (
              <div className={clsx(
                "p-4 rounded-2xl border text-xs font-mono space-y-2",
                testResult.status === "success"
                  ? "bg-emerald-500/5 border-emerald-500/20 text-emerald-400"
                  : "bg-red-500/5 border-red-500/20 text-red-400"
              )}>
                <div className="font-bold uppercase tracking-wider">
                  {testResult.status === "success" ? "Test réussi" : "Test échoué"}
                </div>
                <p>{testResult.message}</p>
                {testResult.details && (
                  <pre className="text-[10px] bg-black/40 p-2 rounded overflow-x-auto text-slate-300">
                    {JSON.stringify(testResult.details, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
