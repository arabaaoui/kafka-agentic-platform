"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createFilterRule, patchFilterRule } from "@/lib/api";
import type { FilterRule } from "@/lib/api";

interface Props {
  rule?: FilterRule;
  onDone: () => void;
}

type CriteriaMode = "jql" | "structured" | "alertmanager";

const EMPTY_FORM = {
  name: "",
  scope: "jira" as "jira" | "alertmanager" | "care",
  priority: 100,
  poll_interval_seconds: 60,
  mode: "jql" as CriteriaMode,
  jql: "",
  am_matchers: "",
  jql_project: "",
  jql_assignee: "",
  jql_status_not: "Closed,Resolved",
  jql_issuetype: "Incident,Bug",
};

function buildCriteria(f: typeof EMPTY_FORM): Record<string, unknown> {
  if (f.scope === "alertmanager") {
    const matchers: Record<string, string> = {};
    for (const pair of f.am_matchers.split("\n")) {
      const [k, ...v] = pair.split("=");
      if (k?.trim()) matchers[k.trim()] = v.join("=").trim();
    }
    return { matchers };
  }
  if (f.mode === "jql") return { jql: f.jql };
  const parts: string[] = [];
  if (f.jql_project) parts.push(`project IN (${f.jql_project})`);
  if (f.jql_assignee) parts.push(`assignee = ${f.jql_assignee}`);
  if (f.jql_issuetype) parts.push(`issuetype IN (${f.jql_issuetype})`);
  if (f.jql_status_not) parts.push(`status NOT IN (${f.jql_status_not})`);
  return { jql: parts.join(" AND ") || "project IS NOT EMPTY" };
}

export function FilterRuleEditor({ rule, onDone }: Props) {
  const qc = useQueryClient();
  const isEdit = !!rule;

  const [form, setForm] = useState(() => {
    if (!rule) return EMPTY_FORM;
    const mode: CriteriaMode =
      rule.scope === "alertmanager" ? "alertmanager" :
      "jql" in rule.criteria ? "jql" : "structured";
    return {
      ...EMPTY_FORM,
      name: rule.name,
      scope: rule.scope as typeof EMPTY_FORM["scope"],
      priority: rule.priority,
      poll_interval_seconds: rule.poll_interval_seconds,
      mode,
      jql: (rule.criteria as { jql?: string }).jql ?? "",
      am_matchers: rule.scope === "alertmanager"
        ? Object.entries((rule.criteria as { matchers?: Record<string, string> }).matchers ?? {})
            .map(([k, v]) => `${k}=${v}`).join("\n")
        : "",
    };
  });

  const set = (field: string, value: unknown) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  const mutation = useMutation({
    mutationFn: () => {
      const body = {
        name: form.name,
        scope: form.scope,
        priority: form.priority,
        poll_interval_seconds: form.poll_interval_seconds,
        criteria: buildCriteria(form),
      };
      return isEdit ? patchFilterRule(rule!.id, body) : createFilterRule(body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["filter-rules"] });
      onDone();
    },
  });

  const scopeMode: CriteriaMode =
    form.scope === "alertmanager" ? "alertmanager" : form.mode;

  return (
    <div className="bg-gray-900 border border-gray-700 rounded p-4 space-y-4">
      <h3 className="text-sm font-semibold text-gray-200">
        {isEdit ? "Edit rule" : "New filter rule"}
      </h3>

      {/* Name */}
      <div className="space-y-1">
        <label className="text-xs text-gray-400">Name</label>
        <input
          value={form.name}
          onChange={(e) => set("name", e.target.value)}
          placeholder="My Kafka incidents"
          className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-amber-500"
        />
      </div>

      {/* Scope + priority */}
      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1">
          <label className="text-xs text-gray-400">Scope</label>
          <select
            value={form.scope}
            onChange={(e) => {
              const s = e.target.value as typeof form.scope;
              set("scope", s);
              if (s === "alertmanager") set("mode", "alertmanager");
              else if (form.mode === "alertmanager") set("mode", "jql");
            }}
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-amber-500"
          >
            <option value="jira">jira</option>
            <option value="alertmanager">alertmanager</option>
            <option value="care">care</option>
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-gray-400">Priority</label>
          <input
            type="number"
            value={form.priority}
            onChange={(e) => set("priority", Number(e.target.value))}
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-amber-500"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-gray-400">Poll interval (s)</label>
          <input
            type="number"
            value={form.poll_interval_seconds}
            onChange={(e) => set("poll_interval_seconds", Number(e.target.value))}
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-amber-500"
          />
        </div>
      </div>

      {/* Criteria */}
      {scopeMode === "alertmanager" ? (
        <div className="space-y-1">
          <label className="text-xs text-gray-400">
            Matchers — one <code className="text-gray-300">key=value</code> per line (regex supported)
          </label>
          <textarea
            value={form.am_matchers}
            onChange={(e) => set("am_matchers", e.target.value)}
            rows={4}
            placeholder={"severity=critical\ncluster=kafkahub-preprod\nalertname=.*Kafka.*"}
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs font-mono text-gray-200 focus:outline-none focus:border-amber-500"
          />
        </div>
      ) : (
        <>
          {/* Jira mode toggle */}
          <div className="flex gap-3 text-xs">
            <button
              onClick={() => set("mode", "jql")}
              className={form.mode === "jql"
                ? "text-amber-400 font-semibold"
                : "text-gray-500 hover:text-gray-300"}
            >
              JQL (free text)
            </button>
            <button
              onClick={() => set("mode", "structured")}
              className={form.mode === "structured"
                ? "text-amber-400 font-semibold"
                : "text-gray-500 hover:text-gray-300"}
            >
              Structured form
            </button>
          </div>

          {form.mode === "jql" ? (
            <div className="space-y-1">
              <label className="text-xs text-gray-400">JQL query</label>
              <textarea
                value={form.jql}
                onChange={(e) => set("jql", e.target.value)}
                rows={3}
                placeholder="project IN (PKH, PHX) AND assignee = ops-user AND status NOT IN ('Closed', 'Resolved')"
                className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs font-mono text-gray-200 focus:outline-none focus:border-amber-500"
              />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-xs text-gray-400">Projects (comma-separated)</label>
                <input
                  value={form.jql_project}
                  onChange={(e) => set("jql_project", e.target.value)}
                  placeholder="PKH, PHX"
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-amber-500"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-gray-400">Assignee</label>
                <input
                  value={form.jql_assignee}
                  onChange={(e) => set("jql_assignee", e.target.value)}
                  placeholder="ops-user"
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-amber-500"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-gray-400">Issue types (comma-separated)</label>
                <input
                  value={form.jql_issuetype}
                  onChange={(e) => set("jql_issuetype", e.target.value)}
                  placeholder="Incident, Bug"
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-amber-500"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-gray-400">Statuses to exclude</label>
                <input
                  value={form.jql_status_not}
                  onChange={(e) => set("jql_status_not", e.target.value)}
                  placeholder="Closed, Resolved"
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-amber-500"
                />
              </div>
            </div>
          )}

          {/* JQL preview */}
          {form.mode === "structured" && (
            <div className="text-xs text-gray-500 bg-gray-800/50 rounded px-2 py-1.5 font-mono">
              {buildCriteria({ ...form, scope: "jira" as const }).jql as string}
            </div>
          )}
        </>
      )}

      {mutation.isError && (
        <p className="text-xs text-red-400">
          {(mutation.error as Error)?.message ?? "Save failed."}
        </p>
      )}

      <div className="flex gap-3 justify-end pt-1">
        <button
          onClick={onDone}
          className="px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200"
        >
          Cancel
        </button>
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending || !form.name.trim()}
          className="px-3 py-1.5 text-xs bg-amber-600 hover:bg-amber-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded"
        >
          {mutation.isPending ? "Saving…" : isEdit ? "Save changes" : "Create rule"}
        </button>
      </div>
    </div>
  );
}
