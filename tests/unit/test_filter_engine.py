"""Unit tests for core/filter_engine.py (spec 002)."""

import pytest

from core.filter_engine import (
    FilterEngine,
    FilterRule,
    FilterResult,
    _alertmanager_matches,
    _jira_matches,
    build_jql,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _rule(
    *,
    id: str = "rule-1",
    tenant: str = "carrefour",
    scope: str = "jira",
    name: str = "test rule",
    enabled: bool = True,
    priority: int = 100,
    criteria: dict | None = None,
) -> FilterRule:
    return FilterRule(
        id=id,
        tenant=tenant,
        scope=scope,
        name=name,
        enabled=enabled,
        priority=priority,
        poll_interval_seconds=60,
        criteria=criteria or {},
    )


# ── build_jql ─────────────────────────────────────────────────────────────────


def test_build_jql_passthrough():
    jql = 'project IN (PHX) AND status != Closed'
    assert build_jql({"jql": jql}) == jql


def test_build_jql_from_structured():
    jql = build_jql({"project": ["PKH", "PHX"], "status": "Open"})
    assert 'project IN ("PKH", "PHX")' in jql
    assert 'status IN ("Open")' in jql


def test_build_jql_with_text():
    jql = build_jql({"text": "kafka broker"})
    assert 'text ~ "kafka broker"' in jql


def test_build_jql_empty():
    assert build_jql({}) == ""


# ── _jira_matches ─────────────────────────────────────────────────────────────


def _jira_issue(project="PHX", assignee="arabaaoui", status="Open", issuetype="Incident"):
    return {
        "key": f"{project}-123",
        "fields": {
            "project": {"key": project},
            "assignee": {"name": assignee},
            "status": {"name": status},
            "issuetype": {"name": issuetype},
        },
    }


def test_jira_matches_all_fields():
    matched, reason = _jira_matches(
        _jira_issue(),
        {"project": ["PKH", "PHX"], "assignee": "arabaaoui", "issuetype": "Incident"},
    )
    assert matched


def test_jira_rejects_wrong_project():
    matched, _ = _jira_matches(
        _jira_issue(project="OTHER"),
        {"project": ["PKH", "PHX"]},
    )
    assert not matched


def test_jira_rejects_wrong_assignee():
    matched, reason = _jira_matches(
        _jira_issue(assignee="someone-else"),
        {"assignee": "arabaaoui"},
    )
    assert not matched
    assert "assignee" in reason


def test_jira_empty_criteria_accepts_all():
    matched, _ = _jira_matches(_jira_issue(), {})
    assert matched


def test_jira_jql_key_ignored_in_local_match():
    # The 'jql' key is for the poller, not local matching — should be skipped
    matched, _ = _jira_matches(
        _jira_issue(project="OTHER"),
        {"jql": "project = PHX", "assignee": "arabaaoui"},
    )
    # Only 'assignee' is locally checked — project not in structured keys → passes
    assert matched


# ── _alertmanager_matches ─────────────────────────────────────────────────────


def _alert(severity="critical", cluster="kafkahub-preprod", alertname="KafkaBrokerDown"):
    return {"status": "firing", "labels": {"severity": severity, "cluster": cluster, "alertname": alertname}}


def test_alertmanager_exact_match():
    matched, _ = _alertmanager_matches(
        _alert(),
        {"matchers": {"severity": "critical", "cluster": "kafkahub-preprod"}},
    )
    assert matched


def test_alertmanager_regex_match():
    matched, _ = _alertmanager_matches(
        _alert(alertname="KafkaBrokerDown"),
        {"matchers": {"alertname": ".*Kafka.*"}},
    )
    assert matched


def test_alertmanager_regex_no_match():
    matched, reason = _alertmanager_matches(
        _alert(alertname="NodeMemoryPressure"),
        {"matchers": {"alertname": ".*Kafka.*"}},
    )
    assert not matched
    assert "alertname" in reason


def test_alertmanager_missing_label_no_match():
    matched, _ = _alertmanager_matches(
        {"labels": {"severity": "critical"}},
        {"matchers": {"cluster": "kafkahub-preprod"}},
    )
    assert not matched


def test_alertmanager_no_matchers_accepts_all():
    matched, _ = _alertmanager_matches(_alert(), {})
    assert matched


def test_alertmanager_invalid_regex():
    matched, reason = _alertmanager_matches(
        _alert(),
        {"matchers": {"severity": "[invalid-regex"}},
    )
    assert not matched
    assert "invalid regex" in reason


# ── FilterEngine.evaluate ─────────────────────────────────────────────────────


def test_engine_returns_first_matching_rule():
    rules = [
        _rule(id="r1", priority=100, criteria={"project": "OTHER"}),
        _rule(id="r2", priority=200, criteria={"project": ["PHX", "PKH"]}),
    ]
    engine = FilterEngine()
    result, evaluated = engine.evaluate(_jira_issue(), rules, "jira")
    assert result.matched
    assert result.rule_id == "r2"
    assert len(evaluated) == 2


def test_engine_no_match():
    rules = [_rule(id="r1", criteria={"project": "NOMATCH"})]
    engine = FilterEngine()
    result, evaluated = engine.evaluate(_jira_issue(), rules, "jira")
    assert not result.matched
    assert result.rule_id is None


def test_engine_skips_disabled_rules():
    rules = [
        _rule(id="r1", enabled=False, criteria={"project": ["PHX"]}),
        _rule(id="r2", enabled=True, criteria={"project": "NOMATCH"}),
    ]
    engine = FilterEngine()
    result, evaluated = engine.evaluate(_jira_issue(), rules, "jira")
    assert not result.matched
    # Only r2 (enabled) should have been evaluated
    evaluated_ids = [r.id for r, _, _ in evaluated]
    assert "r1" not in evaluated_ids
    assert "r2" in evaluated_ids


def test_engine_skips_wrong_scope():
    alertmanager_rule = _rule(id="am", scope="alertmanager", criteria={"matchers": {}})
    engine = FilterEngine()
    result, evaluated = engine.evaluate(_jira_issue(), [alertmanager_rule], "jira")
    assert not result.matched
    assert evaluated == []


def test_engine_priority_ordering():
    """Lower priority number wins when both match."""
    rules = [
        _rule(id="high-pri", priority=50, criteria={}),   # no restrictions → matches
        _rule(id="low-pri", priority=200, criteria={}),
    ]
    engine = FilterEngine()
    result, _ = engine.evaluate(_jira_issue(), rules, "jira")
    assert result.rule_id == "high-pri"


def test_engine_alertmanager_scope():
    rules = [_rule(id="am", scope="alertmanager", criteria={"matchers": {"severity": "critical"}})]
    engine = FilterEngine()
    result, _ = engine.evaluate(_alert(), rules, "alertmanager")
    assert result.matched
    assert result.rule_id == "am"
