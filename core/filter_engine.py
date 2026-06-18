"""FilterEngine — evaluates trigger payloads against runtime filter rules.

Jira scope   : criteria may carry ``jql`` (sent to MCP as-is) or structured
               fields (project, assignee, status, issuetype, labels, priority,
               component).  The engine builds JQL from structured fields and also
               does a lightweight local pre-filter on the raw Jira issue payload.
Alertmanager : criteria carry ``matchers`` — key/value pairs where values are
               treated as regex patterns matched against ``labels`` in the alert.
Care         : criteria carry service/expert-group filters (post-v0).

All evaluation results are logged to ``filter_match_log`` by the caller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FilterRule:
    """Lightweight DTO used inside the engine — mirrors the DB model."""

    id: str
    tenant: str
    scope: str  # jira | alertmanager | care
    name: str
    enabled: bool
    priority: int
    poll_interval_seconds: int
    criteria: dict[str, Any]


@dataclass
class FilterResult:
    matched: bool
    rule_id: str | None = None
    rule_name: str | None = None
    reason: str = ""


# ── JQL building from structured criteria ────────────────────────────────────

_JQL_LIST_FIELDS = ("project", "assignee", "status", "issuetype", "priority", "labels", "component")


def build_jql(criteria: dict[str, Any]) -> str:
    """Return a JQL string from criteria dict.

    If ``criteria`` already carries a ``jql`` key, return it verbatim.
    Otherwise, construct JQL from the structured field list.
    """
    if "jql" in criteria:
        return criteria["jql"]

    clauses: list[str] = []
    for field_name in _JQL_LIST_FIELDS:
        values = criteria.get(field_name)
        if not values:
            continue
        if isinstance(values, str):
            values = [values]
        quoted = ", ".join(f'"{v}"' for v in values)
        clauses.append(f"{field_name} IN ({quoted})")

    if "text" in criteria:
        clauses.append(f'text ~ "{criteria["text"]}"')

    return " AND ".join(clauses) if clauses else ""


# ── Jira local pre-filter ─────────────────────────────────────────────────────


def _jira_matches(payload: dict[str, Any], criteria: dict[str, Any]) -> tuple[bool, str]:
    """Check a raw Jira issue payload against structured criteria (local, no API call).

    Returns (matched, reason).  ``jql`` key is skipped — it's for the poller only.
    Payload is a flat-ish Jira issue dict (fields at top-level or under "fields").
    """
    fields = payload.get("fields", payload)  # support both flat and nested

    for key in _JQL_LIST_FIELDS:
        allowed = criteria.get(key)
        if not allowed:
            continue
        if isinstance(allowed, str):
            allowed = [allowed]

        # Jira API returns project.key, issuetype.name, status.name, etc.
        actual = _extract_jira_field(fields, key)
        if actual is None:
            continue
        if not any(str(a).lower() == str(actual).lower() for a in allowed):
            return False, f"jira field '{key}' value '{actual}' not in {allowed}"

    return True, "all jira criteria matched"


def _extract_jira_field(fields: dict, key: str) -> str | None:
    """Extract a normalised string value from a Jira fields dict."""
    raw = fields.get(key)
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw.get("key") or raw.get("name") or raw.get("id")
    if isinstance(raw, list):
        # labels / components are lists
        if not raw:
            return None
        first = raw[0]
        return first.get("name", str(first)) if isinstance(first, dict) else str(first)
    return str(raw)


# ── Alertmanager local matcher ────────────────────────────────────────────────


def _alertmanager_matches(payload: dict[str, Any], criteria: dict[str, Any]) -> tuple[bool, str]:
    """Match an alertmanager alert against ``matchers`` dict (values = regex).

    The payload is a single alert dict from the Alertmanager POST body, with a
    ``labels`` key containing a flat string→string map.
    """
    matchers: dict[str, str] = criteria.get("matchers", {})
    if not matchers:
        return True, "no matchers defined — accept all"

    labels: dict[str, str] = payload.get("labels", {})
    for label_key, pattern in matchers.items():
        actual = labels.get(label_key, "")
        try:
            if not re.fullmatch(pattern, actual):
                return False, f"label '{label_key}'='{actual}' does not match pattern '{pattern}'"
        except re.error as exc:
            return False, f"invalid regex for '{label_key}': {exc}"

    return True, "all alertmanager matchers matched"


# ── FilterEngine ──────────────────────────────────────────────────────────────


class FilterEngine:
    """Evaluate a trigger payload against an ordered list of rules.

    Rules are evaluated in ascending ``priority`` order.  The first matching
    enabled rule wins; remaining rules are skipped.
    """

    def evaluate(
        self,
        payload: dict[str, Any],
        rules: list[FilterRule],
        scope: str,
    ) -> tuple[FilterResult, list[tuple[FilterRule, bool, str]]]:
        """Return (winning FilterResult, list[(rule, matched, reason)] for all evaluated rules).

        The second element is used by the caller to write ``filter_match_log`` rows.
        """
        evaluated: list[tuple[FilterRule, bool, str]] = []
        active = sorted(
            [r for r in rules if r.enabled and r.scope == scope],
            key=lambda r: r.priority,
        )

        for rule in active:
            matched, reason = self._match(payload, rule.criteria, scope)
            evaluated.append((rule, matched, reason))
            if matched:
                return FilterResult(matched=True, rule_id=rule.id, rule_name=rule.name, reason=reason), evaluated

        return FilterResult(matched=False, reason="no enabled rule matched"), evaluated

    @staticmethod
    def _match(payload: dict[str, Any], criteria: dict[str, Any], scope: str) -> tuple[bool, str]:
        if scope == "jira":
            return _jira_matches(payload, criteria)
        if scope == "alertmanager":
            return _alertmanager_matches(payload, criteria)
        # care and future scopes: accept all for now
        return True, f"scope '{scope}' has no local matcher — accept"
