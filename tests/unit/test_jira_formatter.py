"""Unit tests for core/jira_formatter.py (spec 001 T057)."""

from core.jira_formatter import (
    _first_paragraph,
    _md_table_to_jira,
    format_audit_for_jira,
)

_SAMPLE_AUDIT = """\
# Audit — CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001
**Tenant**: carrefour | **Env**: PREPROD

---

## Executive Summary
PVC kafka-data-0 has reached 91% capacity on kafka-preprod.
Root cause: disk saturation causing broker replication lag.
Urgency: CRITICAL — broker may crash within hours.

---

## Ranked Hypotheses

| Rank | Hypothesis | Confidence | Supporting Agents | Key Evidence |
|------|-----------|:----------:|------------------|-------------|
| 1 | PVC saturation causing broker degradation | 88% | kafka-strimzi + k8s-sre | PVC at 91%, lag 45k |
| 2 | Consumer slow (CPU pressure) | 35% | kafka-strimzi | CPU at 45% |

---

## Recommended Actions
1. Monitor PVC growth rate.
2. Check GCP persistent disk IOPS quota.
"""

_CONFLICT_AUDIT = """\
## Executive Summary
Conflict in agent reports.

## ⚠ CONFLICT DETECTED
kafka-strimzi says broker healthy; k8s-sre says PVC at 95%.

## Ranked Hypotheses
| Rank | Hypothesis | Confidence |
|------|-----------|:----------:|
| 1 | PVC saturation | 70% |
"""

_PARTIAL_AUDIT = """\
⚠ PARTIAL AUDIT — all expert agents failed to produce output.
Mission ID: CARREFOUR-PREPROD-INCIDENT-X-20260510-001
"""


# ── format_audit_for_jira ─────────────────────────────────────────────────────


def test_contains_executive_summary():
    result = format_audit_for_jira(_SAMPLE_AUDIT)
    assert "Executive Summary" in result
    assert "PVC kafka-data-0" in result


def test_contains_ranked_hypotheses_table():
    result = format_audit_for_jira(_SAMPLE_AUDIT)
    assert "Ranked Hypotheses" in result
    assert "PVC saturation" in result
    assert "88%" in result


def test_jira_table_uses_double_pipes_for_header():
    result = format_audit_for_jira(_SAMPLE_AUDIT)
    # Jira header rows use || delimiters
    assert "|| Rank ||" in result or "||Rank||" in result.replace(" ", "")


def test_contains_platform_footer():
    result = format_audit_for_jira(_SAMPLE_AUDIT)
    assert "kafka-agentic-platform v0" in result
    assert "autonomy L2" in result


def test_conflict_banner_when_conflict_present():
    result = format_audit_for_jira(_CONFLICT_AUDIT)
    assert "Conflicting hypotheses" in result or "warning" in result.lower()


def test_partial_audit_warning():
    result = format_audit_for_jira(_PARTIAL_AUDIT)
    assert "Partial audit" in result or "partial" in result.lower()


def test_no_crash_on_empty_audit():
    result = format_audit_for_jira("")
    assert "kafka-agentic-platform" in result  # footer always present


def test_no_crash_on_minimal_audit():
    result = format_audit_for_jira("# Audit\nSome text.")
    assert isinstance(result, str)
    assert len(result) > 0


# ── _md_table_to_jira ─────────────────────────────────────────────────────────


def test_md_table_to_jira_header_row():
    md = "| Rank | Hypothesis | Confidence |\n|------|-----------|:----------:|\n| 1 | PVC sat | 88% |\n"
    result = _md_table_to_jira(md)
    assert "|| Rank || Hypothesis || Confidence ||" in result
    assert "| 1 | PVC sat | 88% |" in result


def test_md_table_separator_row_skipped():
    md = "| A | B |\n|---|---|\n| 1 | 2 |\n"
    result = _md_table_to_jira(md)
    assert "---" not in result


def test_md_table_single_row():
    md = "| A | B |\n|---|---|\n"
    result = _md_table_to_jira(md)
    assert "|| A || B ||" in result


# ── _first_paragraph ──────────────────────────────────────────────────────────


def test_first_paragraph_skips_headings():
    text = "# Heading\n## Sub\nFirst real paragraph."
    assert _first_paragraph(text) == "First real paragraph."


def test_first_paragraph_skips_tables():
    text = "| col |\n| --- |\nReal text."
    assert _first_paragraph(text) == "Real text."


def test_first_paragraph_empty_text():
    assert _first_paragraph("") == ""
