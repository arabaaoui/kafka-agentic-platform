'use client';

import { useEffect, useState } from 'react';
import { 
  Plus, 
  Edit2, 
  Trash2, 
  Activity, 
  Database, 
  Server, 
  Shield, 
  AlertTriangle,
  Settings
} from 'lucide-react';
import { 
  listInfrastructureTenants, 
  upsertInfrastructureEnv, 
  deleteInfrastructureEnv,
  testInfrastructureEnv,
  TenantInfrastructure,
  InfrastructureEnv
} from '@/lib/api';
import { EnvModal } from '@/components/EnvModal';
import { DeleteConfirmModal } from '@/components/DeleteConfirmModal';
import clsx from 'clsx';

export default function TenantsPage() {
  const [tenants, setTenants] = useState<TenantInfrastructure[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal states
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedTenant, setSelectedTenant] = useState<string | null>(null);
  const [selectedEnv, setSelectedEnv] = useState<string | null>(null);
  const [editData, setEditData] = useState<InfrastructureEnv | null>(null);

  // Delete modal states
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [envToDelete, setEnvToDelete] = useState<{tenant: string, slug: string, name: string} | null>(null);
  const [testing, setTesting] = useState<Record<string, boolean>>({});

  const handleTest = async (tenant: string, slug: string) => {
    const key = `${tenant}:${slug}`;
    setTesting(prev => ({ ...prev, [key]: true }));
    try {
        const result = await testInfrastructureEnv(tenant, slug);
        if (result.status === "success") {
            alert(`✅ Success: ${result.message}\n\nToken preview: ${result.details.token_preview}`);
        } else {
            alert(`❌ Error: ${result.message}`);
        }
    } catch (err: any) {
        alert(`❌ Fatal error during test: ${err.message}`);
    } finally {
        setTesting(prev => ({ ...prev, [key]: false }));
    }
  };

  const fetchTenants = async () => {
    try {
      setLoading(true);
      const data = await listInfrastructureTenants();
      setTenants(data);
      setError(null);
    } catch (err: any) {
      console.error('Infra fetch failed:', err);
      setError(`Failed to load infrastructure: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTenants();
  }, []);

  const handleAdd = (tenant: string) => {
    setSelectedTenant(tenant);
    setSelectedEnv(null);
    setEditData(null);
    setIsModalOpen(true);
  };

  const handleEdit = (tenant: string, slug: string, data: InfrastructureEnv) => {
    setSelectedTenant(tenant);
    setSelectedEnv(slug);
    setEditData(data);
    setIsModalOpen(true);
  };

  const handleSave = async (slug: string, data: any) => {
    if (!selectedTenant) return;
    await upsertInfrastructureEnv(selectedTenant, slug, data);
    await fetchTenants();
  };

  const handleDeleteClick = (tenant: string, slug: string, name: string) => {
    setEnvToDelete({ tenant, slug, name });
    setIsDeleteModalOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!envToDelete) return;
    try {
      await deleteInfrastructureEnv(envToDelete.tenant, envToDelete.slug);
      await fetchTenants();
    } catch (err: any) {
      alert(err.message || "Failed to delete environment. System environments (YAML) cannot be deleted.");
    }
  };

  return (
    <div className="space-y-8">
      <header className="flex items-center justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Settings className="w-5 h-5 text-blue-500" />
            Infrastructure Management
          </h1>
          <p className="text-slate-500 text-xs font-medium">Configure environments, clusters, and monitoring endpoints.</p>
        </div>
      </header>

      {loading && tenants.length === 0 ? (
        <div className="grid gap-6">
          <div className="animate-pulse bg-slate-900/50 h-64 rounded-2xl border border-slate-800" />
        </div>
      ) : error ? (
        <div className="bg-red-950/10 border border-red-900/30 rounded-2xl p-12 text-center space-y-4">
          <div className="w-16 h-16 bg-red-500/10 rounded-full flex items-center justify-center mx-auto border border-red-500/20">
            <AlertTriangle className="w-8 h-8 text-red-500" />
          </div>
          <div className="space-y-2">
            <h2 className="text-red-400 font-bold text-lg">Infrastructure Error</h2>
            <p className="text-red-300/60 text-sm max-w-md mx-auto leading-relaxed">{error}</p>
          </div>
          <button 
            onClick={fetchTenants}
            className="px-6 py-2 bg-red-500/10 text-red-400 border border-red-500/20 rounded-xl text-xs font-bold hover:bg-red-500/20 transition-all"
          >
            Retry Connection
          </button>
        </div>
      ) : (
        <div className="grid gap-12">
          {tenants.map(t => (
            <div key={t.tenant} className="space-y-6">
              <div className="flex items-center justify-between px-2">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-blue-600/10 text-blue-400 rounded-xl flex items-center justify-center font-black text-lg border border-blue-500/20 shadow-inner">
                    {t.tenant[0].toUpperCase()}
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-slate-100 tracking-tight">{t.display_name}</h2>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[10px] text-slate-500 font-mono font-bold bg-slate-800/50 px-1.5 py-0.5 rounded border border-slate-700/50">ID: {t.tenant}</span>
                      <span className="w-1 h-1 rounded-full bg-slate-700" />
                      <span className={clsx(
                        "text-[10px] font-bold uppercase tracking-tighter",
                        t.autonomy_level === 'L3' ? "text-emerald-400" : "text-amber-500"
                      )}>
                        Policy: {t.autonomy_level} ({t.autonomy_level === 'L2' ? 'Read-Only' : 'Autonomous'})
                      </span>
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => handleAdd(t.tenant)}
                  className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-xl text-xs font-bold transition-all shadow-lg shadow-blue-600/10 border border-blue-400/20"
                >
                  <Plus className="w-4 h-4" />
                  Add Environment
                </button>
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                {Object.entries(t.envs || {}).map(([envSlug, cfg]) => {
                  if (!cfg) return null;
                  const clusters = Array.isArray(cfg.clusters) ? cfg.clusters : [];
                  
                  return (
                  <div key={envSlug} className="group relative bg-slate-900/40 border border-slate-800 rounded-2xl p-6 hover:bg-slate-900/60 hover:border-slate-700 transition-all duration-300 shadow-sm overflow-hidden">
                    {/* Background decoration */}
                    <div className="absolute top-0 right-0 p-8 -mr-8 -mt-8 opacity-[0.03] group-hover:opacity-[0.05] transition-opacity">
                        <Server className="w-32 h-32 text-white" />
                    </div>

                    <div className="flex items-start justify-between relative z-10 mb-6">
                      <div className="space-y-1">
                        <div className="flex items-center gap-3">
                            <h3 className="text-[11px] font-black text-slate-500 uppercase tracking-[0.2em]">{envSlug}</h3>
                            <span className={clsx(
                                "w-2 h-2 rounded-full shadow-[0_0_8px]",
                                envSlug === 'prod' ? "bg-red-500 shadow-red-500/50" : "bg-emerald-500 shadow-emerald-500/50"
                            )} />
                        </div>
                        <p className="text-sm font-bold text-slate-200">{cfg.display_name || envSlug}</p>
                      </div>
                      
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button 
                          onClick={() => handleTest(t.tenant, envSlug)}
                          disabled={testing[`${t.tenant}:${envSlug}`]}
                          className={clsx(
                            "p-2 text-slate-500 hover:text-emerald-400 hover:bg-emerald-400/10 rounded-lg transition-all",
                            testing[`${t.tenant}:${envSlug}`] && "animate-pulse"
                          )}
                          title="Test connectivity"
                        >
                          <Activity className="w-4 h-4" />
                        </button>
                        <button 
                          onClick={() => handleEdit(t.tenant, envSlug, cfg)}
                          className="p-2 text-slate-500 hover:text-blue-400 hover:bg-blue-400/10 rounded-lg transition-all"
                          title="Edit environment"
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                        <button 
                          onClick={() => handleDeleteClick(t.tenant, envSlug, cfg.display_name)}
                          className="p-2 text-slate-500 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-all"
                          title="Delete override"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                    
                    <div className="space-y-5 relative z-10">
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                            <Database className="w-3 h-3 text-slate-600" />
                            <span className="text-[10px] text-slate-500 font-bold uppercase tracking-tight">Active Clusters</span>
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {clusters.map(c => (
                            <code key={c} className="text-[10px] text-amber-400/90 bg-amber-950/20 px-2 py-0.5 rounded border border-amber-900/30 font-mono font-bold">
                              {c}
                            </code>
                          ))}
                          {clusters.length === 0 && <span className="text-[10px] text-slate-600 italic">No clusters configured</span>}
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-4 pt-4 border-t border-slate-800/60">
                        <div className="space-y-1">
                          <div className="flex items-center gap-1.5">
                            <Activity className="w-3 h-3 text-slate-600" />
                            <span className="text-[9px] text-slate-600 font-bold uppercase">Observability</span>
                          </div>
                          <span className="text-[11px] text-slate-400 truncate font-mono block" title={cfg.prom_url}>{cfg.prom_url || 'N/A'}</span>
                        </div>
                        <div className="space-y-1 text-right">
                          <div className="flex items-center gap-1.5 justify-end">
                            <Shield className="w-3 h-3 text-slate-600" />
                            <span className="text-[9px] text-slate-600 font-bold uppercase">Namespace</span>
                          </div>
                          <span className="text-[11px] text-slate-400 font-mono block">{cfg.kafka_namespace || 'N/A'}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                );})}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modals */}
      <EnvModal 
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSave={handleSave}
        initialData={editData}
        tenantSlug={selectedTenant || ""}
        envSlug={selectedEnv || undefined}
      />

      <DeleteConfirmModal 
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        onConfirm={handleConfirmDelete}
        title="Delete Environment Override"
        description={`Are you sure you want to delete the configuration for ${envToDelete?.name}? This will restore the default YAML configuration if it exists.`}
        resourceId={envToDelete?.name || ""}
      />

      <footer className="mt-12 pt-6 border-t border-slate-900/50">
        <div className="bg-slate-900/40 border border-slate-800/60 rounded-2xl p-5 flex gap-4 items-start shadow-sm">
          <div className="w-8 h-8 bg-blue-600/10 rounded-lg flex items-center justify-center border border-blue-500/20">
             <Shield className="w-4 h-4 text-blue-400" />
          </div>
          <div className="space-y-1">
            <h4 className="text-xs font-bold text-blue-400 uppercase tracking-tight">Configuration Lifecycle</h4>
            <p className="text-[11px] text-slate-400/80 leading-relaxed max-w-2xl">
              Infrastructure environments are loaded from <code>tenants/*.yaml</code>.
              Adding or modifying an environment here creates an <strong>override in the database</strong> which takes precedence. 
              Deleting an override restores the original system configuration.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
