"use client";

import { useState, useEffect } from "react";
import { X, Save, Server, Shield, Activity, Database, Key, FileText, Globe, User } from "lucide-react";
import clsx from "clsx";

interface EnvFormData {
  display_name: string;
  badge_color: string;
  clusters: string;
  kubeconfig: string;
  kubeconfig_content: string;
  target_gsa_email: string;
  kafka_namespace: string;
  prom_url: string;
  proxy_url: string;
  proxy_user: string;
  proxy_pass: string;
  vm_url: string;
}

interface EnvModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (slug: string, data: any) => Promise<void>;
  initialData?: any;
  tenantSlug: string;
  envSlug?: string;
}

export function EnvModal({ isOpen, onClose, onSave, initialData, tenantSlug, envSlug }: EnvModalProps) {
  const [formData, setFormData] = useState<EnvFormData>({
    display_name: "",
    badge_color: "gray",
    clusters: "",
    kubeconfig: "/app/kube_conf/kubeconfig.yaml",
    kubeconfig_content: "",
    target_gsa_email: "",
    kafka_namespace: "kafka",
    prom_url: "http://phenix-k8s-lab:30090",
    proxy_url: "",
    proxy_user: "",
    proxy_pass: "",
    vm_url: "http://phenix-k8s-lab:30090",
  });
  
  const [currentEnvSlug, setCurrentEnvSlug] = useState(envSlug || "");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (initialData) {
      setFormData({
        display_name: initialData.display_name || "",
        badge_color: initialData.badge_color || "gray",
        clusters: Array.isArray(initialData.clusters) ? initialData.clusters.join(", ") : "",
        kubeconfig: initialData.kubeconfig || "",
        kubeconfig_content: initialData.kubeconfig_content || "",
        target_gsa_email: initialData.target_gsa_email || "",
        kafka_namespace: initialData.kafka_namespace || "",
        prom_url: initialData.prom_url || "",
        proxy_url: initialData.proxy_url || "",
        proxy_user: initialData.proxy_user || "",
        proxy_pass: initialData.proxy_pass || "",
        vm_url: initialData.vm_url || "",
      });
      setCurrentEnvSlug(envSlug || "");
    } else {
        setFormData({
            display_name: "",
            badge_color: "gray",
            clusters: "",
            kubeconfig: "/app/kube_conf/kubeconfig.yaml",
            kubeconfig_content: "",
            target_gsa_email: "",
            kafka_namespace: "kafka",
            prom_url: "http://phenix-k8s-lab:30090",
            proxy_url: "",
            proxy_user: "",
            proxy_pass: "",
            vm_url: "http://phenix-k8s-lab:30090",
        });
        setCurrentEnvSlug("");
    }
  }, [initialData, envSlug, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        ...formData,
        clusters: formData.clusters.split(",").map(c => c.trim()).filter(c => c !== ""),
      };
      await onSave(currentEnvSlug, payload);
      onClose();
    } catch (err) {
      console.error(err);
      alert("Failed to save environment");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        <header className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-blue-600/20 rounded-lg flex items-center justify-center">
              <Server className="w-4 h-4 text-blue-400" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white tracking-tight">
                {envSlug ? `Edit ${formData.display_name}` : "New Infrastructure Environment"}
              </h2>
              <p className="text-[10px] text-slate-500 uppercase font-bold tracking-widest">Tenant: {tenantSlug}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 text-slate-500 hover:text-white hover:bg-slate-800 rounded-xl transition-colors">
            <X className="w-5 h-5" />
          </button>
        </header>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto">
          <div className="p-6 space-y-8">
            {/* Basic Info */}
            <section className="space-y-4">
              <div className="flex items-center gap-2 text-blue-400">
                <Database className="w-4 h-4" />
                <h3 className="text-sm font-bold uppercase tracking-wider">Identity & Naming</h3>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-[10px] text-slate-500 font-bold uppercase ml-1">Unique Slug (ID)</label>
                  <input
                    required
                    disabled={!!envSlug}
                    value={currentEnvSlug}
                    onChange={(e) => setCurrentEnvSlug(e.target.value.toLowerCase().replace(/[^a-z0-h-]/g, ''))}
                    placeholder="e.g. staging-bloc4"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50 transition-colors disabled:opacity-50 disabled:bg-slate-900"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[10px] text-slate-500 font-bold uppercase ml-1">Display Name</label>
                  <input
                    required
                    value={formData.display_name}
                    onChange={(e) => setFormData({...formData, display_name: e.target.value})}
                    placeholder="e.g. GKE — STAGING (BLOC 4)"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50 transition-colors"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] text-slate-500 font-bold uppercase ml-1">Target GSA Email (Impersonation)</label>
                <div className="relative">
                  <User className="absolute left-3 top-2.5 w-4 h-4 text-slate-600" />
                  <input
                    value={formData.target_gsa_email}
                    onChange={(e) => setFormData({...formData, target_gsa_email: e.target.value})}
                    placeholder="e.g. expert-agent@project.iam.gserviceaccount.com"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-4 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50 transition-colors font-mono"
                  />
                </div>
                <p className="text-[9px] text-slate-500 italic ml-1">Leave empty to use the platform's default identity.</p>
              </div>
            </section>

            {/* Kubernetes & Kafka */}
            <section className="space-y-4">
              <div className="flex items-center gap-2 text-emerald-400">
                <Shield className="w-4 h-4" />
                <h3 className="text-sm font-bold uppercase tracking-wider">Kubernetes & Kafka</h3>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-[10px] text-slate-500 font-bold uppercase ml-1">Kafka Namespace</label>
                  <input
                    required
                    value={formData.kafka_namespace}
                    onChange={(e) => setFormData({...formData, kafka_namespace: e.target.value})}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50 transition-colors font-mono"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[10px] text-slate-500 font-bold uppercase ml-1">Cluster IDs (Comma separated)</label>
                  <input
                    required
                    value={formData.clusters}
                    onChange={(e) => setFormData({...formData, clusters: e.target.value})}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50 transition-colors font-mono text-[11px]"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] text-slate-500 font-bold uppercase ml-1 flex items-center gap-1.5">
                  <FileText className="w-3 h-3" />
                  Kubeconfig Content (YAML)
                </label>
                <textarea
                  required
                  value={formData.kubeconfig_content}
                  onChange={(e) => setFormData({...formData, kubeconfig_content: e.target.value})}
                  rows={6}
                  placeholder="apiVersion: v1..."
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50 transition-colors font-mono leading-relaxed"
                />
              </div>
            </section>

            {/* Monitoring */}
            <section className="space-y-4">
              <div className="flex items-center gap-2 text-amber-400">
                <Activity className="w-4 h-4" />
                <h3 className="text-sm font-bold uppercase tracking-wider">Observability</h3>
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] text-slate-500 font-bold uppercase ml-1">Prometheus API URL</label>
                <div className="relative">
                  <Globe className="absolute left-3 top-2.5 w-4 h-4 text-slate-600" />
                  <input
                    required
                    value={formData.prom_url}
                    onChange={(e) => setFormData({...formData, prom_url: e.target.value})}
                    placeholder="https://prometheus.internal.carrefour.com"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-4 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50 transition-colors font-mono"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] text_slate-500 font-bold uppercase ml-1">HTTP Proxy URL (Optional)</label>
                <div className="relative">
                  <Globe className="absolute left-3 top-2.5 w-4 h-4 text-slate-600" />
                  <input
                    value={formData.proxy_url}
                    onChange={(e) => setFormData({...formData, proxy_url: e.target.value})}
                    placeholder="http://proxy.carrefour.com:4239"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-4 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50 transition-colors font-mono"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-[10px] text-slate-500 font-bold uppercase ml-1">Proxy User</label>
                  <input
                    value={formData.proxy_user}
                    onChange={(e) => setFormData({...formData, proxy_user: e.target.value})}
                    placeholder="username"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50 transition-colors font-mono"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[10px] text-slate-500 font-bold uppercase ml-1">Proxy Password</label>
                  <input
                    type="password"
                    value={formData.proxy_pass}
                    onChange={(e) => setFormData({...formData, proxy_pass: e.target.value})}
                    placeholder="••••••••"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50 transition-colors font-mono"
                  />
                </div>
              </div>
            </section>
          </div>

          <footer className="px-6 py-4 border-t border-slate-800 bg-slate-900/50 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-bold text-slate-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600 text-white px-6 py-2 rounded-xl text-sm font-bold flex items-center gap-2 transition-all shadow-lg shadow-blue-900/20"
            >
              {loading ? <Activity className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {envSlug ? "Update Configuration" : "Create Environment"}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}
