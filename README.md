# kafka-agentic-platform

**OS agentique** pour l'auto-triage et la capitalisation d'incidents Kafka/Strimzi/GKE.

Transforme des alertes brutes en hypothèses rankées et actionnables en < 5 minutes, avec isolation stricte des environnements, mémoire RAG persistante et niveau d'autonomie configurable.

> **Stack :** Google ADK 2.2 · LiteLLM · FastAPI · PostgreSQL + pgvector · Next.js 14 · gemini-2.5-flash-lite

---

## Architecture globale

```mermaid
flowchart TD
    subgraph TRIG["Déclencheurs"]
        JM["Jira MCP Poller\nc4-atlassian SSE · 60s"]
        AM["Alertmanager\nWebhook POST · Poller HTTP"]
    end

    subgraph FE["Filter Engine"]
        FR["Filter Rules DB\npriority · criteria JSONB"]
        JQL["JQL Builder\nJira structured → JQL"]
        LOG["filter_match_log"]
    end

    DB[("triggers\nPostgreSQL\nfile durable\nSKIP LOCKED")]

    subgraph WORK["N Workers async — WORKER_CONCURRENCY"]
        W["claim_next()\nSELECT FOR UPDATE SKIP LOCKED\n→ lease 900s · at-least-once"]
    end

    subgraph PIPE["Pipeline ADK"]
        IA["① IntakeAgent\nclassify() → tenant · env · cluster · type · subject"]
        subgraph PAR["② asyncio.gather — 3 experts en parallèle"]
            KE["KafkaStrimziExpert\nlag · ISR · URP · PVC · KRaft"]
            SRE["K8sGcpSreAgent\npods · events · nodes · GKE"]
            PT["PromAlertsTriage\nPromRules · faux positifs · topic filter"]
        end
        EC["③ EvidenceConsolidator\naudit.md — hypothèses rankées par probabilité"]
        PM["④ PostMortemAgent  opt-in\nBRIEF.md · KB card · RAG ingest"]
    end

    subgraph OUT["Outputs"]
        UI["Next.js UI\nKanban · détail mission · SSE live"]
        JIRA["Jira comment\nopt-in"]
        PGV[("PostgreSQL + pgvector\nmissions · audits · kb_chunks\nRAG multilingual-e5-small")]
        LF["Langfuse\ntraces LLM · tokens · coûts"]
    end

    JM -->|payload| FE
    AM -->|payload| FE
    FE -->|first-match wins| DB
    DB --> WORK
    WORK --> PIPE
    IA --> PAR
    PAR --> EC
    EC --> PM
    PIPE --> UI
    PIPE --> JIRA
    PM --> PGV
    PIPE --> LF
    PIPE --> PGV
```

---

## Cycle de vie d'une mission

```mermaid
stateDiagram-v2
    direction LR

    [*] --> En_attente : alerte reçue + filtre OK\ntrigger INSERT matched=true

    En_attente --> Reservee : claim_next()\nSELECT FOR UPDATE SKIP LOCKED\nclaimed_at · claimed_by

    Reservee --> OPEN : IntakeAgent classify()\nMissionContext.create()\nmissions INSERT

    OPEN --> CLOSED : EvidenceConsolidator\naudit.md produit\ntous les experts OK

    OPEN --> PARTIAL : consolidation partielle\nun ou plusieurs experts KO

    CLOSED --> Finalisee : PostMortemAgent\nBRIEF.md · KB card · RAG

    PARTIAL --> Finalisee : PostMortemAgent\nBRIEF.md · KB card · RAG

    Reservee --> En_echec : max_attempts dépassé\nlast_error = DEAD:reason

    En_echec --> En_attente : retry manuel\nreset claimed_at · attempts · last_error
```

---

## Chaîne de plugins ADK

Chaque agent exécute les 6 plugins suivants dans l'ordre garanti par `build_plugin_list()` :

```mermaid
flowchart TD
    REQ(["Requête LLM entrante"]) --> P1

    P1["① AutonomyPlugin\nbloque les writes si autonomy_level < L3"]
    P2["② IsolationPlugin\nrejette tout accès cross-env\nPREPROD → PROD interdit"]
    P3["③ ToolParamInjector\ninjecte kubeconfig · prom_url · token\ndans chaque tool call automatiquement"]
    P4["④ AuditPlugin\njournalise chaque event en JSONL\nsecrets redactés avant écriture"]
    P5["⑤ RAGPreInjector\nrecherche sémantique dans pgvector\npré-injecte le contexte KB pertinent"]
    P6["⑥ LangfusePlugin\nauto-tracing LLM\nprompts · latences · token counts · coûts"]

    P1 --> P2 --> P3 --> P4 --> P5 --> P6

    P6 --> LLM["LlmAgent ADK\ngemini-2.5-flash-lite"]
    LLM -->|tool calls| TK["kafka-agent-toolkit\nprom_query · k8s_client\nlag_correlation · pvc_forecast\ncluster_health · promrule_audit"]
    TK --> LLM
    LLM --> REPORT(["Rapport .md"])
```

---

## Mission ID

Chaque mission reçoit un identifiant structuré et humainement lisible :

```
CARREFOUR - PREPROD - INCIDENT - PVC-SATURATION - 20260520 - 001
    │           │         │             │               │       │
 TENANT        ENV      TYPE         SUBJECT          DATE    SEQ
               │                  kebab-case
           lab · preprod         max 30 chars
             · prod
```

---

## Niveaux d'autonomie

```mermaid
flowchart LR
    L1["L1 — Read-only strict\nprom_query\ncluster_health get/describe\n\nUsage : Production"]
    L2["L2 — Read + logs\nL1 + kubectl logs/top\n\nUsage : Défaut opérationnel"]
    L3["L3 — Supervisé\nActions réversibles\navec confirmation humaine\n\nUsage : Lab"]
    L4["L4 — Full autonomy\nToutes actions\n\nDésactivé en production"]

    L1 -->|"niveau supérieur"| L2 --> L3 --> L4
```

---

## Lien kafka-agent-toolkit

```mermaid
graph LR
    subgraph KAP["kafka-agentic-platform  (ce repo)"]
        IA["IntakeAgent"]
        KE["KafkaStrimziExpert"]
        SRE["K8sGcpSreAgent"]
        PT["PromAlertsTriage"]
        ORC["PipelineOrchestrator"]
    end

    subgraph KAT["kafka-agent-toolkit"]
        PQ["prom_query"]
        KC["k8s_client"]
        LC["lag_correlation"]
        PF["pvc_forecast"]
        CH["cluster_health"]
        PA["promrule_audit"]
        KB["kb/ — schémas + CRUD"]
        SK["skills/ — SKILL.md loader\npromql_kafka · promql_k8s"]
    end

    KAP -->|"import uv workspace\ndépendance unidirectionnelle"| KAT
```

---

## Structure des répertoires

```
kafka-agentic-platform/
│
├── agents/                        ← Agents ADK (LlmAgent)
│   ├── base.py                    ← BaseAgent : SKILL.md + plugins + persist
│   ├── intake/                    ← LLM pur — classifieur tenant/env/type/subject
│   ├── kafka_strimzi_expert/      ← lag · URP · ISR · PVC · KRaft · brokers
│   ├── k8s_gcp_sre/               ← pods · events · nodes · PVC GKE · ressources
│   ├── prom_alerts_triage/        ← PromRules · faux positifs · topic filter
│   ├── evidence_consolidator/     ← synthèse → audit.md hypothèses rankées
│   ├── post_mortem_analyst/       ← BRIEF.md + KB card + RAG ingest
│   └── pipeline/
│       ├── orchestrator.py        ← PipelineOrchestrator.handle()
│       ├── durable_queue.py       ← claim_next() SKIP LOCKED · lease · retry
│       └── worker.py              ← poll DB · heartbeat · backoff exponentiel
│
├── api/                           ← FastAPI application
│   ├── main.py                    ← create_app() · lifespan (workers + pollers)
│   └── routes/
│       ├── missions.py            ← /v1/missions · kanban · lifecycle · finalize
│       ├── triggers.py            ← /v1/triggers · retry
│       ├── filter_rules.py        ← /v1/filter-rules CRUD
│       ├── kb.py                  ← /v1/kb browse
│       ├── metrics.py             ← GET /metrics Prometheus
│       └── admin.py               ← GET /healthz · worker_count · queue_depth
│
├── core/                          ← Services partagés
│   ├── mission.py                 ← MissionContext · MissionStatus · MissionType
│   ├── models.py                  ← SQLAlchemy ORM — 12 tables
│   ├── plugins.py                 ← build_plugin_list() — 6 ADK BasePlugin
│   ├── filter_engine.py           ← FilterEngine · FilterRule · JQL builder
│   ├── rag_ingest.py              ← ingest_kb_card() · ingest_audit()
│   ├── embeddings.py              ← EmbeddingService (multilingual-e5-small)
│   ├── mem0_bridge.py             ← RAGIndex — recherche sémantique pgvector
│   ├── kb_writer.py               ← KBCardWriter — create/update/index
│   ├── tenant.py                  ← TenantRegistry · TenantConfig · EnvConfig
│   └── gcp.py                     ← GCPTokenProvider — ADC / GSA impersonation
│
├── triggers/                      ← Sources d'entrée
│   ├── alertmanager_webhook.py    ← POST /webhooks/alertmanager (202 immédiat)
│   ├── alertmanager_poller.py     ← poll HTTP périodique
│   └── jira_mcp_poller.py         ← SSE c4-atlassian MCP
│
├── web/                           ← Frontend Next.js 14 + React 18
│   ├── app/
│   │   ├── page.tsx               ← Dashboard (OpsStrip + Kanban)
│   │   ├── missions/              ← Liste table | Kanban 4 colonnes
│   │   ├── missions/[id]/         ← Détail + lifecycle + audit.md + agents
│   │   ├── triggers/              ← Historique triggers
│   │   ├── kb/                    ← Explorer KB cards
│   │   └── monitoring/            ← Métriques temps réel (Recharts)
│   └── components/
│       ├── OpsStrip.tsx           ← workers · queue · oldest pending · dead count
│       ├── MissionsKanban.tsx     ← En attente / Réservée / Terminée / En échec
│       ├── MissionLifecycle.tsx   ← Timeline trigger → mission
│       └── AuditViewer.tsx        ← Rendu Markdown audit.md
│
├── migrations/                    ← Alembic — 14 migrations
├── kb/incidents/                  ← Knowledge Base Markdown (cartes incidents)
├── tenants/                       ← Configs multi-tenant YAML
├── evals/                         ← Harness Promptfoo (CI gate ≥ 80%)
├── tests/                         ← unit/ + integration/ + e2e/
└── deploy/
    ├── docker-compose.yml         ← postgres · redis · backend · web (profiles: app, lab)
    ├── Dockerfile.backend
    └── helm/                      ← Chart Helm K8s
```

---

## API REST

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/v1/missions` | Liste des missions (filtrable status/env/tenant) |
| `GET` | `/v1/missions/kanban` | Vue Kanban 4 colonnes en une requête |
| `GET` | `/v1/missions/{id}` | Détail mission + agents + audit |
| `GET` | `/v1/missions/{id}/lifecycle` | Timeline trigger → mission |
| `POST` | `/v1/missions/{id}/finalize` | Déclenche PostMortemAgent |
| `DELETE` | `/v1/missions/{id}` | Suppression mission + cascade |
| `GET` | `/v1/triggers` | Historique triggers |
| `POST` | `/v1/triggers/{id}/retry` | Relance un trigger DEAD |
| `GET` | `/v1/filter-rules` | Liste des règles de filtrage |
| `POST` | `/v1/filter-rules` | Crée une règle |
| `GET` | `/v1/kb` | Browse KB cards |
| `GET` | `/metrics` | Métriques Prometheus scrape |
| `GET` | `/healthz` | Santé plateforme (worker_count · queue_depth · dead_count) |

---

## Installation

### Prérequis

- Docker Compose v2
- Python 3.11+ + [uv](https://docs.astral.sh/uv/)
- [`kafka-agent-toolkit`](https://github.com/arabaaoui/kafka-agent-toolkit) cloné en parallèle
- GCP credentials (ADC ou Service Account)

### Démarrage

```bash
# 1. Cloner les deux repos côte à côte (uv workspace)
git clone https://github.com/arabaaoui/kafka-agentic-platform
git clone https://github.com/arabaaoui/kafka-agent-toolkit

# 2. Configurer l'environnement
cp kafka-agentic-platform/.env.example kafka-agentic-platform/.env
# Remplir : GOOGLE_API_KEY, JIRA_MCP_TOKEN, LANGFUSE_SECRET_KEY, ...

# 3. Démarrer l'infrastructure (postgres + redis + langfuse)
cd kafka-agentic-platform/deploy
docker compose up postgres redis langfuse -d

# 4. Appliquer les migrations DB
cd .. && uv run alembic upgrade head

# 5. Démarrer backend + frontend
cd deploy && docker compose --profile app up
```

| Service | URL |
|---------|-----|
| Frontend (Next.js) | http://localhost:3000 |
| Backend (FastAPI) | http://localhost:8001 |
| Langfuse | http://localhost:3001 |
| API docs | http://localhost:8001/docs |

### Tests

```bash
# Tests unitaires back-end (186 tests)
uv run pytest tests/unit/ -q

# Évaluations LLM (gate ≥ 80%)
cd evals && bash run_evals.sh

# Vérification TypeScript front-end
cd web && npx tsc --noEmit --skipLibCheck
```

---

→ [kafka-agent-toolkit](https://github.com/arabaaoui/kafka-agent-toolkit) — bibliothèque stateless des primitives métier
