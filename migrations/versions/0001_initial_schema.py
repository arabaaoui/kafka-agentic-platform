"""Initial schema — all platform tables + bootstrap filter rule.

Revision ID: 0001
Revises:
Create Date: 2026-05-10
"""

from __future__ import annotations

from alembic import op

revision: str = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # missions_seq — atomic MISSION_ID counter
    op.execute("""
        CREATE TABLE IF NOT EXISTS missions_seq (
            tenant        TEXT    NOT NULL,
            env           TEXT    NOT NULL,
            type          TEXT    NOT NULL,
            subject       TEXT    NOT NULL,
            mission_date  DATE    NOT NULL,
            seq           INT     NOT NULL DEFAULT 1,
            PRIMARY KEY (tenant, env, type, subject, mission_date)
        )
    """)

    # triggers
    op.execute("""
        CREATE TABLE IF NOT EXISTS triggers (
            id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant        TEXT        NOT NULL,
            source        TEXT        NOT NULL CHECK (source IN ('jira','alertmanager','care')),
            external_id   TEXT        NOT NULL,
            payload       JSONB       NOT NULL DEFAULT '{}',
            matched       BOOLEAN     NOT NULL DEFAULT FALSE,
            mission_id    TEXT,
            received_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            processed_at  TIMESTAMPTZ,
            UNIQUE (tenant, source, external_id)
        )
    """)

    # missions
    op.execute("""
        CREATE TABLE IF NOT EXISTS missions (
            id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            mission_id     TEXT        NOT NULL UNIQUE,
            tenant         TEXT        NOT NULL,
            env            TEXT        NOT NULL,
            cluster        TEXT        NOT NULL DEFAULT '',
            type           TEXT        NOT NULL,
            subject        TEXT        NOT NULL,
            status         TEXT        NOT NULL DEFAULT 'OPEN'
                                       CHECK (status IN ('OPEN','CLOSED','PARTIAL')),
            autonomy_level TEXT        NOT NULL DEFAULT 'L2',
            trigger_id     UUID        REFERENCES triggers(id),
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            closed_at      TIMESTAMPTZ,
            metadata       JSONB       NOT NULL DEFAULT '{}'
        )
    """)

    # audits
    op.execute("""
        CREATE TABLE IF NOT EXISTS audits (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            mission_id      TEXT        NOT NULL REFERENCES missions(mission_id),
            agent           TEXT        NOT NULL DEFAULT '',
            content_md      TEXT        NOT NULL DEFAULT '',
            posted_jira     BOOLEAN     NOT NULL DEFAULT FALSE,
            jira_comment_id TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # agent_outputs
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_outputs (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            mission_id  TEXT        NOT NULL REFERENCES missions(mission_id),
            agent       TEXT        NOT NULL,
            output_json JSONB       NOT NULL DEFAULT '{}',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # filter_rules
    op.execute("""
        CREATE TABLE IF NOT EXISTS filter_rules (
            id                    UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant                TEXT    NOT NULL,
            scope                 TEXT    NOT NULL CHECK (scope IN ('jira','alertmanager','care')),
            name                  TEXT    NOT NULL,
            enabled               BOOLEAN NOT NULL DEFAULT TRUE,
            priority              INT     NOT NULL DEFAULT 100,
            poll_interval_seconds INT     NOT NULL DEFAULT 60,
            criteria              JSONB   NOT NULL,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by            TEXT
        )
    """)

    # filter_match_log
    op.execute("""
        CREATE TABLE IF NOT EXISTS filter_match_log (
            id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
            rule_id     UUID    REFERENCES filter_rules(id),
            trigger_id  UUID    REFERENCES triggers(id),
            matched     BOOLEAN NOT NULL,
            matched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            reason      TEXT
        )
    """)

    # indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_missions_tenant_env ON missions (tenant, env)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_missions_status ON missions (status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_triggers_source ON triggers (source, matched)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_filter_rules_tenant ON filter_rules (tenant, scope, enabled)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audits_mission ON audits (mission_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_outputs_mission ON agent_outputs (mission_id)")

    # Bootstrap Jira filter rule for tenant carrefour
    op.execute("""
        INSERT INTO filter_rules (tenant, scope, name, enabled, priority, criteria, created_by)
        VALUES (
            'carrefour', 'jira', 'Mes incidents Kafka (bootstrap)', TRUE, 100,
            '{"jql": "project IN (PKH, PHX) AND assignee = arabaaoui AND issuetype IN (''Incident'', ''Bug'') AND status NOT IN (''Closed'', ''Resolved'') AND created >= -7d"}'::jsonb,
            'system'
        )
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    for table in (
        "filter_match_log", "filter_rules", "agent_outputs",
        "audits", "missions", "triggers", "missions_seq",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
