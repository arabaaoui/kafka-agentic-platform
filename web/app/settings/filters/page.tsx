"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listFilterRules, patchFilterRule, deleteFilterRule } from "@/lib/api";
import type { FilterRule } from "@/lib/api";
import { FilterRuleEditor } from "@/components/FilterRuleEditor";

export default function FiltersPage() {
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<FilterRule | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["filter-rules"],
    queryFn: () => listFilterRules(),
    refetchInterval: 30_000,
  });

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      patchFilterRule(id, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["filter-rules"] }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteFilterRule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["filter-rules"] }),
  });

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-base font-bold text-white">Filter rules</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Changes take effect on the next poller cycle — no restart required.
          </p>
        </div>
        <button
          onClick={() => { setCreating(true); setEditing(null); }}
          className="px-3 py-1.5 text-xs bg-amber-600 hover:bg-amber-500 text-white rounded"
        >
          + New rule
        </button>
      </div>

      {/* Inline editor — create */}
      {creating && (
        <FilterRuleEditor onDone={() => setCreating(false)} />
      )}

      {isLoading && (
        <p className="text-gray-500 text-xs py-8">Loading rules…</p>
      )}

      {isError && (
        <p className="text-red-400 text-sm py-8">
          Could not load filter rules — is the API running?
        </p>
      )}

      {data && data.length === 0 && !creating && (
        <div className="py-16 text-center text-gray-600 text-sm">
          No rules yet.
          <p className="text-xs mt-1">Click "New rule" to create your first filter.</p>
        </div>
      )}

      {data && data.length > 0 && (
        <div className="space-y-3">
          {data
            .slice()
            .sort((a, b) => a.priority - b.priority)
            .map((rule) => (
              <div key={rule.id}>
                {editing?.id === rule.id ? (
                  <FilterRuleEditor rule={rule} onDone={() => setEditing(null)} />
                ) : (
                  <RuleCard
                    rule={rule}
                    onToggle={() => toggle.mutate({ id: rule.id, enabled: !rule.enabled })}
                    onEdit={() => { setEditing(rule); setCreating(false); }}
                    onDelete={() => {
                      if (confirm(`Delete rule "${rule.name}"?`)) remove.mutate(rule.id);
                    }}
                    isToggling={toggle.isPending}
                    isDeleting={remove.isPending}
                  />
                )}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

function RuleCard({
  rule, onToggle, onEdit, onDelete, isToggling, isDeleting,
}: {
  rule: FilterRule;
  onToggle: () => void;
  onEdit: () => void;
  onDelete: () => void;
  isToggling: boolean;
  isDeleting: boolean;
}) {
  const criteria = rule.criteria as Record<string, unknown>;
  const criteriaPreview = criteria.jql
    ? String(criteria.jql).slice(0, 90)
    : criteria.matchers
    ? JSON.stringify(criteria.matchers).slice(0, 90)
    : JSON.stringify(criteria).slice(0, 90);

  return (
    <div className={`border rounded p-3 transition-colors ${
      rule.enabled ? "border-gray-700 bg-gray-900" : "border-gray-800 bg-gray-950 opacity-60"
    }`}>
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1 flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-semibold text-gray-200">{rule.name}</span>
            <ScopeBadge scope={rule.scope} />
            <span className="text-xs text-gray-600">p={rule.priority}</span>
            {rule.poll_interval_seconds && (
              <span className="text-xs text-gray-600">poll={rule.poll_interval_seconds}s</span>
            )}
          </div>
          <p className="text-xs font-mono text-gray-500 truncate" title={criteriaPreview}>
            {criteriaPreview}{criteriaPreview.length >= 90 ? "…" : ""}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={onToggle}
            disabled={isToggling}
            className={`w-8 h-4 rounded-full transition-colors relative ${
              rule.enabled ? "bg-amber-500" : "bg-gray-700"
            } disabled:opacity-50`}
            title={rule.enabled ? "Disable" : "Enable"}
          >
            <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all ${
              rule.enabled ? "left-4" : "left-0.5"
            }`} />
          </button>
          <button
            onClick={onEdit}
            className="text-xs text-gray-500 hover:text-gray-300 px-1"
          >
            Edit
          </button>
          <button
            onClick={onDelete}
            disabled={isDeleting}
            className="text-xs text-gray-600 hover:text-red-400 px-1 disabled:opacity-50"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

function ScopeBadge({ scope }: { scope: string }) {
  const style: Record<string, string> = {
    jira:          "bg-blue-900/50 text-blue-300 border-blue-700",
    alertmanager:  "bg-red-900/50 text-red-300 border-red-700",
    care:          "bg-violet-900/50 text-violet-300 border-violet-700",
  };
  const cls = style[scope.toLowerCase()] ?? "bg-gray-800 text-gray-400 border-gray-700";
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded border text-xs ${cls}`}>
      {scope}
    </span>
  );
}
