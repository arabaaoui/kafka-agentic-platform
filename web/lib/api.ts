const isServer = typeof window === "undefined";

// When on server (SSR), hit backend directly via Docker network.
// When on client (Browser), hit the same host via Next.js proxy rewrite.
const BASE = isServer ? (process.env.API_INTERNAL_URL || "http://backend:8000") : "";

export type MissionStatus = "OPEN" | "CLOSED" | "PARTIAL";
export type MissionType = "INCIDENT" | "INVESTIGATION" | "MAINTENANCE" | "REVIEW";
export type Env = "PREPROD" | "PROD" | "REC" | "DEV" | "LAB";

export interface Mission {
  id: string;
  mission_id: string;
  tenant: string;
  env: string;
  cluster: string;
  type: MissionType;
  subject: string;
  status: MissionStatus;
  autonomy_level: string;
  trigger_id: string | null;
  trigger_type?: string;
  created_at: string;
  closed_at: string | null;
}

export interface AgentOutputSummary {
  id: string;
  agent: string;
  created_at: string;
}

export interface AuditMeta {
  id: string;
  agent: string;
  posted_jira: boolean;
  jira_comment_id: string | null;
  kb_card_slug?: string | null;
  created_at: string;
  updated_at: string;
}

export interface MissionDetail extends Mission {
  metadata_: Record<string, unknown>;
  agent_outputs: AgentOutputSummary[];
  audit: AuditMeta | null;
}

export interface MissionListResponse {
  items: Mission[];
  total: number;
  limit: number;
  offset: number;
}

export interface FilterRule {
  id: string;
  tenant: string;
  scope: "jira" | "alertmanager" | "care";
  name: string;
  enabled: boolean;
  priority: number;
  poll_interval_seconds: number;
  criteria: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  created_by: string | null;
}

export interface FilterRuleCreate {
  tenant?: string;
  scope: "jira" | "alertmanager" | "care";
  name: string;
  enabled?: boolean;
  priority?: number;
  poll_interval_seconds?: number;
  criteria: Record<string, unknown>;
}

export interface Trigger {
  id: string;
  tenant: string;
  source: string;
  external_id: string;
  matched: boolean;
  mission_id: string | null;
  received_at: string;
  processed_at: string | null;
  reject_reason?: string | null;
}

export interface TriggerListResponse {
  items: Trigger[];
  total: number;
  limit: number;
  offset: number;
}


// ── Fetch helpers ─────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE}${path}`;
  console.log(`[API] Fetching ${url}`);
  
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body}`);
  }
  if (res.status === 204) {
    return {} as T;
  }
  return res.json() as Promise<T>;
}

// ── Missions ──────────────────────────────────────────────────────────────────

export async function listMissions(params?: {
  status?: string; env?: string; limit?: number; offset?: number;
}): Promise<MissionListResponse> {
  const q = new URLSearchParams();
  if (params?.status) q.set("status", params.status);
  if (params?.env) q.set("env", params.env);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  return apiFetch<MissionListResponse>(`/v1/missions?${q}`);
}

export async function getMission(id: string): Promise<MissionDetail> {
  return apiFetch<MissionDetail>(`/v1/missions/${encodeURIComponent(id)}`);
}

export async function getAuditMarkdown(missionId: string): Promise<string | null> {
  const url = `${BASE}/v1/missions/${encodeURIComponent(missionId)}/audit`;
  const res = await fetch(url);
  if (res.status === 202) return null; // still running
  if (!res.ok) throw new Error(`Audit ${res.status}`);
  return res.text();
}

export async function postToJira(missionId: string): Promise<void> {
  await apiFetch(`/v1/missions/${encodeURIComponent(missionId)}/post-to-jira`, { method: "POST" });
}

export async function finalizeMission(missionId: string): Promise<any> {
  return apiFetch(`/v1/missions/${encodeURIComponent(missionId)}/finalize`, { method: "POST" });
}

// ── Filter rules ──────────────────────────────────────────────────────────────

export async function listFilterRules(params?: {
  tenant?: string; scope?: string;
}): Promise<FilterRule[]> {
  const q = new URLSearchParams();
  if (params?.tenant) q.set("tenant", params.tenant);
  if (params?.scope) q.set("scope", params.scope);
  return apiFetch<FilterRule[]>(`/v1/filter-rules?${q}`);
}

export async function createFilterRule(body: FilterRuleCreate): Promise<FilterRule> {
  return apiFetch<FilterRule>("/v1/filter-rules", { method: "POST", body: JSON.stringify(body) });
}

export async function patchFilterRule(id: string, patch: Partial<FilterRule>): Promise<FilterRule> {
  return apiFetch<FilterRule>(`/v1/filter-rules/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
}

export async function deleteFilterRule(id: string): Promise<void> {
  await apiFetch(`/v1/filter-rules/${id}`, { method: "DELETE" });
}

// ── Triggers ──────────────────────────────────────────────────────────────────

export async function listTriggers(params?: {
  source?: string; matched?: boolean; limit?: number; offset?: number;
}): Promise<TriggerListResponse> {
  const q = new URLSearchParams();
  if (params?.source) q.set("source", params.source);
  if (params?.matched !== undefined) q.set("matched", String(params.matched));
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  return apiFetch<TriggerListResponse>(`/v1/triggers?${q}`);
}

export async function listIgnoredTriggers(params?: {
  source?: string; limit?: number; offset?: number;
}): Promise<TriggerListResponse> {
  const q = new URLSearchParams();
  if (params?.source) q.set("source", params.source);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  return apiFetch<TriggerListResponse>(`/v1/triggers/ignored?${q}`);
}

export async function deleteMission(missionId: string): Promise<void> {
  return apiFetch<void>(`/v1/missions/${encodeURIComponent(missionId)}`, {
    method: "DELETE",
  });
}

export async function deleteKBCard(slug: string): Promise<void> {
  return apiFetch<void>(`/v1/kb/cards/${encodeURIComponent(slug)}`, {
    method: "DELETE",
  });
}

export async function getSystemAuditLogs(params?: { 
  limit?: number; 
  offset?: number;
  action?: string;
  resourceType?: string;
}): Promise<any> {
  const q = new URLSearchParams();
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  if (params?.action) q.set("action", params.action);
  if (params?.resourceType) q.set("resource_type", params.resourceType);
  return apiFetch<any>(`/v1/admin/audit?${q}`);
}

// ── Infrastructure ────────────────────────────────────────────────────────────

export interface InfrastructureEnv {
  id?: string;
  tenant: string;
  slug: string;
  display_name: string;
  badge_color: string;
  clusters: string[];
  kubeconfig: string;
  kafka_namespace: string;
  prom_url: string;
  proxy_url?: string;
  target_gsa_email?: string;
  vm_url: string;
  created_at?: string;
  updated_at?: string;
}

export interface TenantInfrastructure {
  tenant: string;
  display_name: string;
  autonomy_level: string;
  envs: Record<string, InfrastructureEnv>;
}

export async function listInfrastructureTenants(): Promise<TenantInfrastructure[]> {
  return apiFetch<TenantInfrastructure[]>("/v1/infrastructure/tenants");
}

export async function upsertInfrastructureEnv(tenant: string, slug: string, data: any): Promise<InfrastructureEnv> {
  return apiFetch<InfrastructureEnv>(`/v1/infrastructure/tenants/${tenant}/envs/${slug}`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deleteInfrastructureEnv(tenant: string, slug: string): Promise<void> {
  await apiFetch(`/v1/infrastructure/tenants/${tenant}/envs/${slug}`, {
    method: "DELETE",
  });
}

export async function testInfrastructureEnv(tenant: string, slug: string): Promise<any> {
  return apiFetch(`/v1/infrastructure/tenants/${tenant}/envs/${slug}/test`, {
    method: "POST",
  });
}

export async function reloadTenants(): Promise<{ status: string; tenants: string[] }> {
  return apiFetch<{ status: string; tenants: string[] }>("/v1/admin/reload-tenants", {
    method: "POST",
  });
}

// ── Health & OpsStrip ─────────────────────────────────────────────────────────

export interface HealthStatus {
  status: string;
  tenants: string[];
  worker_count: number;
  queue_depth: number | null;
  oldest_pending_age_seconds: number | null;
  dead_count: number;
}

export async function getHealthz(): Promise<HealthStatus> {
  return apiFetch<HealthStatus>("/healthz");
}

// ── Kanban ────────────────────────────────────────────────────────────────────

export interface KanbanTrigger {
  id: string;
  tenant: string;
  source: string;
  external_id: string;
  received_at: string;
  claimed_at: string | null;
  claimed_by: string | null;
  attempts: number;
  last_error: string | null;
  mission_id: string | null;
}

export interface KanbanMission {
  mission_id: string;
  tenant: string;
  env: string;
  subject: string;
  status: string;
  created_at: string;
  closed_at: string | null;
}

export interface KanbanView {
  en_attente: KanbanTrigger[];
  reservee: KanbanTrigger[];
  terminee: KanbanMission[];
  en_echec: KanbanTrigger[];
}

export async function getMissionsKanban(): Promise<KanbanView> {
  return apiFetch<KanbanView>("/v1/missions/kanban");
}

export async function retryTrigger(triggerId: string): Promise<{ id: string; tenant: string; source: string; status: string }> {
  return apiFetch(`/v1/triggers/${encodeURIComponent(triggerId)}/retry`, { method: "POST" });
}

// ── Mission Lifecycle ─────────────────────────────────────────────────────────

export interface MissionLifecycle {
  trigger_id: string | null;
  received_at: string | null;
  claimed_at: string | null;
  claimed_by: string | null;
  attempts: number;
  last_error: string | null;
  mission_created_at: string | null;
  mission_closed_at: string | null;
  mission_status: string;
}

export async function getMissionLifecycle(missionId: string): Promise<MissionLifecycle> {
  return apiFetch<MissionLifecycle>(`/v1/missions/${encodeURIComponent(missionId)}/lifecycle`);
}

// ── Metrics Snapshot ──────────────────────────────────────────────────────────

export interface MetricsDataPoint {
  ts: string;
  depth: number;
  inflight: number;
}

export interface MetricsSnapshot {
  queue_depth: number;
  queue_inflight: number;
  oldest_pending_age_seconds: number | null;
  mission_completed_24h: number;
  mission_dead_total: number;
  duration_p50_seconds: number | null;
  duration_p95_seconds: number | null;
  duration_p99_seconds: number | null;
  history: MetricsDataPoint[];
}

export async function getMetricsSnapshot(): Promise<MetricsSnapshot> {
  return apiFetch<MetricsSnapshot>("/v1/metrics/snapshot");
}

// ── Agents & Skills Catalog ───────────────────────────────────────────────────

export interface AgentCard {
  name: string;
  agent_dir: string;
  description: string;
  version: string;
  description_long: string;
  active: boolean;
}

export interface SkillCard {
  agent_name: string;
  agent_dir: string;
  category: string;
  skills: string[];
}

export async function getAgentsCatalog(): Promise<AgentCard[]> {
  return apiFetch<AgentCard[]>("/v1/admin/agents/catalog");
}

export async function getSkillsCatalog(): Promise<SkillCard[]> {
  return apiFetch<SkillCard[]>("/v1/admin/skills/catalog");
}
