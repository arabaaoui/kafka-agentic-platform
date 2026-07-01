"""Pydantic response/request schemas for the REST API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Missions ──────────────────────────────────────────────────────────────────


class MissionSummary(BaseModel):
    id: uuid.UUID
    mission_id: str
    tenant: str
    env: str
    cluster: str
    type: str
    subject: str
    status: str
    autonomy_level: str
    trigger_id: uuid.UUID | None
    created_at: datetime
    closed_at: datetime | None

    model_config = {"from_attributes": True}


class AgentOutputSummary(BaseModel):
    id: uuid.UUID
    agent: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditSummary(BaseModel):
    id: uuid.UUID
    agent: str
    posted_jira: bool
    jira_comment_id: str | None
    created_at: datetime
    updated_at: datetime
    brief_path: str | None = None
    kb_card_slug: str | None = None
    finalized_at: datetime | None = None

    model_config = {"from_attributes": True}


class MissionDetail(MissionSummary):
    metadata_: dict[str, Any] = Field(alias="metadata_")
    agent_outputs: list[AgentOutputSummary] = []
    audit: AuditSummary | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class MissionListResponse(BaseModel):
    items: list[MissionSummary]
    total: int
    limit: int
    offset: int


# ── Audits ────────────────────────────────────────────────────────────────────


class AuditResponse(BaseModel):
    id: uuid.UUID
    mission_id: str
    agent: str
    content_md: str
    posted_jira: bool
    jira_comment_id: str | None
    created_at: datetime
    updated_at: datetime
    brief_path: str | None = None
    kb_card_slug: str | None = None
    finalized_at: datetime | None = None


# ── Filter rules ──────────────────────────────────────────────────────────────


class FilterRuleCreate(BaseModel):
    tenant: str = "enterprise"
    scope: Literal["jira", "alertmanager", "care"]
    name: str
    enabled: bool = True
    priority: int = 100
    poll_interval_seconds: int = 60
    criteria: dict[str, Any]


class FilterRulePatch(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    priority: int | None = None
    poll_interval_seconds: int | None = None
    criteria: dict[str, Any] | None = None


class FilterRuleResponse(BaseModel):
    id: uuid.UUID
    tenant: str
    scope: str
    name: str
    enabled: bool
    priority: int
    poll_interval_seconds: int
    criteria: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    created_by: str | None

    model_config = {"from_attributes": True}


# ── Triggers ──────────────────────────────────────────────────────────────────


class TriggerResponse(BaseModel):
    id: uuid.UUID
    tenant: str
    source: str
    external_id: str
    matched: bool
    mission_id: str | None
    received_at: datetime
    processed_at: datetime | None
    claimed_at: datetime | None = None
    claimed_by: str | None = None
    attempts: int = 0
    last_error: str | None = None

    model_config = {"from_attributes": True}


class IgnoredTriggerResponse(TriggerResponse):
    reject_reason: str | None = None


class TriggerListResponse(BaseModel):
    items: list[TriggerResponse]
    total: int
    limit: int
    offset: int


class IgnoredTriggerListResponse(BaseModel):
    items: list[IgnoredTriggerResponse]
    total: int
    limit: int
    offset: int


# ── Post-mortem / finalize ─────────────────────────────────────────────────────


class FinalizeResult(BaseModel):
    mission_id: str
    brief_path: str
    kb_card_slug: str | None
    kb_card_action: Literal["created", "updated", "skipped", "error"]
    kb_index_card_count: int
    finalized_at: datetime


# ── KB cards ──────────────────────────────────────────────────────────────────


class KBCardSummary(BaseModel):
    slug: str
    title: str
    theme: str
    severity: str
    occurrences: int
    last_mission: str


class KBCardListResponse(BaseModel):
    items: list[KBCardSummary]
    total: int
    limit: int
    offset: int


# ── System Audit ─────────────────────────────────────────────────────────────


class SystemAuditResponse(BaseModel):
    id: uuid.UUID
    action: str
    resource_type: str
    resource_id: str
    audit_metadata: dict
    created_at: datetime
    created_by: str | None

    class Config:
        from_attributes = True


class SystemAuditListResponse(BaseModel):
    items: list[SystemAuditResponse]
    total: int
    limit: int
    offset: int


# ── Infrastructure ────────────────────────────────────────────────────────────


class InfrastructureEnvCreate(BaseModel):
    display_name: str
    badge_color: str = "gray"
    clusters: list[str]
    kubeconfig: str
    kube_context: str = ""
    kubeconfig_content: str = ""
    kafka_namespace: str = ""
    prom_url: str
    alertmanager_url: str = ""
    proxy_url: str = ""
    proxy_user: str = ""
    proxy_pass: str = ""
    target_gsa_email: str = ""
    vm_url: str = ""


class InfrastructureEnvResponse(InfrastructureEnvCreate):
    id: uuid.UUID
    tenant: str
    slug: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TenantInfrastructureResponse(BaseModel):
    tenant: str
    display_name: str
    autonomy_level: str
    envs: dict[str, InfrastructureEnvResponse | Any] # Mix of DB and YAML models


# ── Kanban / Durable Queue ────────────────────────────────────────────────────


class KanbanTrigger(BaseModel):
    id: uuid.UUID
    tenant: str
    source: str
    external_id: str
    received_at: datetime
    claimed_at: datetime | None
    claimed_by: str | None
    attempts: int
    last_error: str | None
    mission_id: str | None

    model_config = {"from_attributes": True}


class KanbanMission(BaseModel):
    mission_id: str
    tenant: str
    env: str
    subject: str
    status: str
    created_at: datetime
    closed_at: datetime | None

    model_config = {"from_attributes": True}


class KanbanView(BaseModel):
    en_attente: list[KanbanTrigger]
    reservee: list[KanbanTrigger]
    terminee: list[KanbanMission]
    en_echec: list[KanbanTrigger]


class MissionLifecycle(BaseModel):
    trigger_id: str | None
    received_at: datetime | None
    claimed_at: datetime | None
    claimed_by: str | None
    attempts: int
    last_error: str | None
    mission_created_at: datetime | None
    mission_closed_at: datetime | None
    mission_status: str


class RetryResult(BaseModel):
    id: str
    tenant: str
    source: str
    status: str = "retried"


# ── Metrics Snapshot ──────────────────────────────────────────────────────────


class MetricsDataPoint(BaseModel):
    ts: str
    depth: int
    inflight: int


class MetricsSnapshot(BaseModel):
    queue_depth: int
    queue_inflight: int
    oldest_pending_age_seconds: float | None
    mission_completed_24h: int
    mission_dead_total: int
    duration_p50_seconds: float | None
    duration_p95_seconds: float | None
    duration_p99_seconds: float | None
    history: list[MetricsDataPoint]


# ── Admin / Agents Catalog ────────────────────────────────────────────────────


class AgentCard(BaseModel):
    name: str
    agent_dir: str
    description: str
    version: str
    description_long: str
    active: bool = True


class SkillCard(BaseModel):
    agent_name: str
    agent_dir: str
    category: str
    skills: list[str]
