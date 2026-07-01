"""Mission context — the primary runtime object threaded through all agents and plugins.

MISSION_ID format: {TENANT}-{ENV}-{TYPE}-{SUBJECT}-{YYYYMMDD}-{SEQ:03d}
Example: ENTERPRISE-PREPROD-INCIDENT-PVC-SATURATION-20260510-001

Subject validation reuses the kebab-case slug regex from kafka-agent-toolkit,
with max_len=30 (spec 003 FR-002). This is a regression guard for the production bug
where YAML template comments leaked into the slug (spec 003 SC-005).
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

try:
    from kafka_agent_toolkit.kb.schemas import SLUG_PATTERN, validate_slug, MAX_LEN_MISSION_SUBJECT
except ImportError:
    import re as _re
    SLUG_PATTERN = _re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
    MAX_LEN_MISSION_SUBJECT = 64
    def validate_slug(v: str, **kwargs: Any) -> str:
        return v.split("#")[0].strip()

_MISSION_ID_RE = re.compile(
    r"^[A-Z0-9]+-[A-Z]+-[A-Z]+-[A-Z0-9-]+-\d{8}-\d{3}$"
)


class MissionType(str, Enum):
    INCIDENT = "INCIDENT"
    MAINTENANCE = "MAINTENANCE"
    INVESTIGATION = "INVESTIGATION"
    REVIEW = "REVIEW"


class MissionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PARTIAL = "PARTIAL"


def _validate_subject(value: str) -> str:
    """Wrapper to use toolkit validation logic."""
    return validate_slug(value, max_len=MAX_LEN_MISSION_SUBJECT)


class MissionContext(BaseModel):
    """Runtime context for a mission — passed to all agents and plugins."""

    mission_id: str
    tenant: str
    env: str
    cluster: str
    type: MissionType
    subject: str
    status: MissionStatus = MissionStatus.OPEN
    trigger_id: UUID | None = None
    autonomy_level: str = "L2"
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)
    db_session: Any | None = Field(default=None, exclude=True)

    @field_validator("subject", mode="before")
    @classmethod
    def _validate_subject(cls, v: str) -> str:
        return _validate_subject(v)

    @field_validator("mission_id")
    @classmethod
    def _validate_mission_id_format(cls, v: str) -> str:
        if not _MISSION_ID_RE.match(v):
            raise ValueError(
                f"Invalid MISSION_ID format: {v!r}. "
                "Expected: TENANT-ENV-TYPE-SUBJECT-YYYYMMDD-SEQ "
                "(e.g. ENTERPRISE-PREPROD-INCIDENT-PVC-SATURATION-20260510-001)"
            )
        return v

    @field_validator("env", "tenant")
    @classmethod
    def _uppercase(cls, v: str) -> str:
        return v.upper()

    model_config = {"frozen": True}

    def __deepcopy__(self, memo: dict[int, Any]) -> MissionContext:
        """Preserve db_session as-is. ADK 2.x deepcopies session.state which contains
        MissionContext; AsyncSession holds non-picklable socket file descriptors."""
        import copy
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        
        copied_dict = {}
        for k, v in self.__dict__.items():
            if k == "db_session":
                copied_dict[k] = v  # Keep as-is (do not deepcopy the database session)
            else:
                copied_dict[k] = copy.deepcopy(v, memo)
                
        object.__setattr__(result, "__dict__", copied_dict)
        return result

    @staticmethod
    async def create(
        *,
        db_conn: Any,
        tenant: str,
        env: str,
        cluster: str,
        type: MissionType,
        subject: str,
        trigger_id: UUID | None = None,
        autonomy_level: str = "L2",
        metadata: dict[str, Any] | None = None,
    ) -> "MissionContext":
        """Generate ID, persist to DB, and return a new context (SQLAlchemy-safe)."""
        mid = await generate_mission_id(
            tenant=tenant, env=env, type=type, subject=subject, db_conn=db_conn
        )
        
        from sqlalchemy import text
        
        # Persist the actual mission record using named parameters.
        # Explicitly JSON-serialize metadata because asyncpg + text() doesn't do it automatically.
        await db_conn.execute(
            text("""
                INSERT INTO missions (mission_id, tenant, env, cluster, type, subject, status, autonomy_level, trigger_id, metadata)
                VALUES (:mid, :tenant, :env, :cluster, :type, :subject, :status, :autonomy_level, :trigger_id, cast(:metadata AS jsonb))
            """),
            {
                "mid": mid,
                "tenant": tenant.upper(),
                "env": env.upper(),
                "cluster": cluster,
                "type": type.value,
                "subject": subject,
                "status": MissionStatus.OPEN.value,
                "autonomy_level": autonomy_level,
                "trigger_id": trigger_id,
                "metadata": json.dumps(metadata or {}),
            }
        )

        return MissionContext(
            mission_id=mid,
            tenant=tenant,
            env=env,
            cluster=cluster,
            type=type,
            subject=subject,
            trigger_id=trigger_id,
            autonomy_level=autonomy_level,
            metadata=metadata or {},
            db_session=db_conn,
        )


def build_mission_id(
    tenant: str,
    env: str,
    type: MissionType,
    subject: str,
    mission_date: date,
    seq: int,
) -> str:
    """Format a MISSION_ID from its components (pure function, no DB)."""
    return (
        f"{tenant.upper()}-{env.upper()}-{type.value}"
        f"-{subject.upper()}-{mission_date.strftime('%Y%m%d')}-{seq:03d}"
    )


async def generate_mission_id(
    *,
    tenant: str,
    env: str,
    type: MissionType,
    subject: str,
    db_conn: Any,
) -> str:
    """Generate a unique MISSION_ID with an atomic Postgres counter (SQLAlchemy-safe)."""
    subject = _validate_subject(subject)
    today = date.today()

    from sqlalchemy import text

    result = await db_conn.execute(
        text("""
            INSERT INTO missions_seq (tenant, env, type, subject, mission_date, seq)
            VALUES (:tenant, :env, :type, :subject, :mission_date, 1)
            ON CONFLICT (tenant, env, type, subject, mission_date)
            DO UPDATE SET seq = missions_seq.seq + 1
            RETURNING seq
        """),
        {
            "tenant": tenant.upper(),
            "env": env.upper(),
            "type": type.value,
            "subject": subject,
            "mission_date": today,
        }
    )
    row = result.fetchone()
    seq: int = row[0]
    return build_mission_id(tenant, env, type, subject, today, seq)
