-- 0001_initial.sql — initial schema for kafka-agentic-platform v0
-- Apply with: psql $DATABASE_URL -f migrations/versions/0001_initial.sql

BEGIN;

-- ── Atomic MISSION_ID sequence counter (spec 003 FR-008) ─────────────────────

CREATE TABLE IF NOT EXISTS missions_seq (
    tenant        TEXT        NOT NULL,
    env           TEXT        NOT NULL,
    type          TEXT        NOT NULL,
    subject       TEXT        NOT NULL,
    mission_date  DATE        NOT NULL,
    seq           INT         NOT NULL DEFAULT 1,
    PRIMARY KEY (tenant, env, type, subject, mission_date)
);

-- ── Triggers ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS triggers (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant        TEXT        NOT NULL,
    source        TEXT        NOT NULL CHECK (source IN ('jira', 'alertmanager', 'care')),
    external_id   TEXT        NOT NULL,               -- Jira key / alert fingerprint
    payload       JSONB       NOT NULL DEFAULT '{}',
    matched       BOOLEAN     NOT NULL DEFAULT FALSE,
    mission_id    TEXT,                               -- set when a mission is created
    received_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at  TIMESTAMPTZ,
    UNIQUE (tenant, source, external_id)
);

-- ── Missions ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS missions (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    mission_id    TEXT        NOT NULL UNIQUE,        -- CARREFOUR-PREPROD-INCIDENT-…
    tenant        TEXT        NOT NULL,
    env           TEXT        NOT NULL,
    cluster       TEXT        NOT NULL DEFAULT '',
    type          TEXT        NOT NULL,
    subject       TEXT        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'OPEN'
                              CHECK (status IN ('OPEN', 'CLOSED', 'PARTIAL')),
    autonomy_level TEXT       NOT NULL DEFAULT 'L2',
    trigger_id    UUID        REFERENCES triggers(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at     TIMESTAMPTZ,
    metadata      JSONB       NOT NULL DEFAULT '{}'
);

-- ── Audits ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audits (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    mission_id    TEXT        NOT NULL REFERENCES missions(mission_id),
    agent         TEXT        NOT NULL DEFAULT '',
    content_md    TEXT        NOT NULL DEFAULT '',    -- ranked hypotheses Markdown
    posted_jira   BOOLEAN     NOT NULL DEFAULT FALSE,
    jira_comment_id TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Agent outputs (intermediate, per-agent) ───────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_outputs (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    mission_id    TEXT        NOT NULL REFERENCES missions(mission_id),
    agent         TEXT        NOT NULL,
    output_json   JSONB       NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Filter rules (spec 002 — configurable runtime via UI) ─────────────────────

CREATE TABLE IF NOT EXISTS filter_rules (
    id                    UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant                TEXT    NOT NULL,
    scope                 TEXT    NOT NULL CHECK (scope IN ('jira', 'alertmanager', 'care')),
    name                  TEXT    NOT NULL,
    enabled               BOOLEAN NOT NULL DEFAULT TRUE,
    priority              INT     NOT NULL DEFAULT 100,
    poll_interval_seconds INT     NOT NULL DEFAULT 60,
    criteria              JSONB   NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by            TEXT
);

-- ── Filter match log ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS filter_match_log (
    id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id     UUID    REFERENCES filter_rules(id),
    trigger_id  UUID    REFERENCES triggers(id),
    matched     BOOLEAN NOT NULL,
    matched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason      TEXT
);

-- ── Indexes ───────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_missions_tenant_env    ON missions (tenant, env);
CREATE INDEX IF NOT EXISTS idx_missions_status        ON missions (status);
CREATE INDEX IF NOT EXISTS idx_triggers_source        ON triggers (source, matched);
CREATE INDEX IF NOT EXISTS idx_filter_rules_tenant    ON filter_rules (tenant, scope, enabled);
CREATE INDEX IF NOT EXISTS idx_audits_mission         ON audits (mission_id);
CREATE INDEX IF NOT EXISTS idx_agent_outputs_mission  ON agent_outputs (mission_id);

-- ── Bootstrap: default Jira filter rule for tenant "carrefour" (spec 002 US1) ─

INSERT INTO filter_rules (tenant, scope, name, enabled, priority, criteria, created_by)
VALUES (
    'carrefour',
    'jira',
    'Mes incidents Kafka (bootstrap)',
    TRUE,
    100,
    '{"jql": "project IN (PKH, PHX) AND assignee = arabaaoui AND issuetype IN (''Incident'', ''Bug'') AND status NOT IN (''Closed'', ''Resolved'') AND created >= -7d"}'::jsonb,
    'system'
)
ON CONFLICT DO NOTHING;

COMMIT;
