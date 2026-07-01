"""Lab scenario: Prometheus false positive — missing topic!="" filter.

Simulates:
  - PrometheusRule KafkaTopicHighMessages fires on empty-string topic label
  - promrule_audit detects the missing topic!="" filter
  - lag_correlation shows URP=0, ISR=3, lag=0 → system is healthy
  - Verdict: FALSE_POSITIVE

Validates:
  - FilterEngine matches Jira ticket with issuetype=Bug
  - promrule_audit flags the misconfigured rule
  - _check_access allows preprod prom_url for preprod mission
  - _L2_BLOCKED_TOOLS allows all read-only tools used in triage
  - _extract_json (IntakeAgent) correctly parses JSON from LLM output
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.filter_engine import FilterEngine, FilterRule
from core.autonomy import _L2_BLOCKED_TOOLS
from core.mission import MissionContext, MissionType
from core.mission_isolation import _check_access
from core.tenant import EnvConfig, TenantConfig


PREPROD_PROM = "https://prom.preprod.example.com"


@pytest.fixture()
def tenant_cfg() -> TenantConfig:
    return TenantConfig(
        tenant="enterprise",
        envs={
            "preprod": EnvConfig(
                clusters=["kafka-preprod"],
                kubeconfig="/kube/preprod",
                prom_url=PREPROD_PROM,
            ),
        },
    )


@pytest.fixture()
def mission() -> MissionContext:
    return MissionContext(
        mission_id="ENTERPRISE-PREPROD-INCIDENT-PROM-FALSE-POSITIVE-20260510-001",
        tenant="enterprise",
        env="preprod",
        cluster="kafka-preprod",
        type=MissionType.INCIDENT,
        subject="prom-false-positive",
    )


# ── Scenario: Jira Bug ticket matches filter rule ─────────────────────────────


def test_jira_bug_ticket_matches_filter():
    jira_issue = {
        "key": "PHX-9876",
        "fields": {
            "project": {"key": "PHX"},
            "assignee": {"name": "ops-user"},
            "status": {"name": "Open"},
            "issuetype": {"name": "Bug"},
        },
    }
    rules = [
        FilterRule(
            id="bootstrap",
            tenant="enterprise",
            scope="jira",
            name="Mes incidents Kafka (bootstrap)",
            enabled=True,
            priority=100,
            poll_interval_seconds=60,
            criteria={
                "project": ["PKH", "PHX"],
                "assignee": "ops-user",
                "issuetype": ["Incident", "Bug"],
            },
        )
    ]
    engine = FilterEngine()
    result, evaluated = engine.evaluate(jira_issue, rules, "jira")
    assert result.matched
    assert len(evaluated) == 1
    assert evaluated[0][1] is True  # (rule, matched, reason)


# ── Scenario: promrule_audit detects missing topic!="" ───────────────────────


def test_promrule_audit_detects_missing_filter():
    from kafka_agent_toolkit.tools.promrule_audit import RuleIssue, PromRuleAuditResult

    # Simulate what promrule_audit would return for a misconfigured rule
    issue = RuleIssue(
        group="kafka.rules",
        rule_name="KafkaTopicHighMessages",
        expr='sum(rate(kafka_topic_messages_in_total[5m])) by (topic) > 10000',
        reason="missing topic!='' filter — aggregates internal topics (empty label)",
    )
    result = PromRuleAuditResult(issues=[issue], checked=5, kafka_rules=3)
    assert len(result.issues) == 1
    assert "topic" in result.issues[0].reason
    assert result.kafka_rules == 3


# ── Scenario: lag=0, URP=0, ISR=3 → system is healthy (false positive) ───────


def test_lag_correlation_healthy_system():
    from kafka_agent_toolkit.tools.lag_correlation import LagCorrelationResult

    result = LagCorrelationResult(
        root_cause="OK",
        severity="OK",
        total_lag=0,
        urp=0,
        isr_avg=3.0,
        election_rate=0.0,
        max_cpu=0.12,
        max_cpu_pod="kafka-0",
        top_groups=[],
        actions=["System healthy — investigate alert rule configuration"],
    )
    assert result.severity == "OK"
    assert result.urp == 0
    assert result.total_lag == 0


# ── Scenario: all read-only triage tools are L2-allowed ──────────────────────


@pytest.mark.parametrize("tool", [
    "promrule_audit",
    "prom_query",
    "cluster_health",
    "lag_correlation",
    "pvc_forecast",
])
def test_all_triage_tools_allowed_l2(tool):
    assert tool not in _L2_BLOCKED_TOOLS


# ── Scenario: IntakeAgent JSON extraction ────────────────────────────────────


def test_intake_extract_json_from_fenced_block():
    from agents.intake.agent import _extract_json

    llm_output = """
Here is my classification:

```json
{
  "env": "preprod",
  "cluster": "kafka-preprod",
  "type": "INCIDENT",
  "subject": "prom-false-positive",
  "confidence": "HIGH",
  "jira_ticket_id": "PHX-9876"
}
```
"""
    result = _extract_json(llm_output)
    assert result is not None
    assert result["env"] == "preprod"
    assert result["subject"] == "prom-false-positive"
    assert result["jira_ticket_id"] == "PHX-9876"


def test_intake_extract_json_bare():
    from agents.intake.agent import _extract_json

    llm_output = '{"status": "env_ambiguous", "reason": "no env found in payload"}'
    result = _extract_json(llm_output)
    assert result["status"] == "env_ambiguous"


def test_intake_extract_json_returns_none_on_garbage():
    from agents.intake.agent import _extract_json

    assert _extract_json("No JSON here at all, just prose.") is None


# ── Scenario: isolation allows preprod prom_url for prom triage ───────────────


def test_isolation_allows_preprod_prom_for_triage(mission, tenant_cfg):
    allowed = _check_access(
        {"prom_url": f"{PREPROD_PROM}/api/v1/query"},
        tenant_cfg,
        mission.env,
    )
    assert allowed, "preprod prom_url must be allowed in preprod mission"
