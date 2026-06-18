# Modèle de Données — 013-hermes-ui-refonte

## Entités existantes (non modifiées)

### Mission (table `missions`)
| Champ | Type | Description |
|---|---|---|
| mission_id | String | Identifiant métier unique |
| tenant | String | Locataire |
| env | String | Environnement (PROD/PREPROD/...) |
| status | String | OPEN / CLOSED / PARTIAL |
| subject | String | Sujet de l'investigation |
| created_at | DateTime | Création |
| closed_at | DateTime? | Clôture (null si en cours) |

### Trigger (table `triggers`) — colonnes ajoutées par migration spec-011
| Champ | Type | Description |
|---|---|---|
| id | UUID | Clé primaire |
| tenant | String | Locataire |
| source | String | jira / alertmanager / care |
| external_id | String | Identifiant externe |
| matched | Boolean | Accepté par les filtres |
| mission_id | String? | Mission associée |
| received_at | DateTime | Réception |
| processed_at | DateTime? | Traitement terminé (null = en file) |
| claimed_at | DateTime? | **NEW** — Réservation par worker |
| claimed_by | String? | **NEW** — Worker ID |
| attempts | Int | **NEW** — Nombre de tentatives |
| last_error | String? | **NEW** — Erreur, LIKE 'DEAD:%' si épuisé |

**Note** : Les colonnes `claimed_at`, `claimed_by`, `attempts`, `last_error` sont dans la DB (migration spec-011) mais PAS encore dans le mapping SQLAlchemy `core/models.py:Trigger`. Le plan spec-013 ajoute ce mapping.

---

## Nouvelles structures de données (API)

### HealthStatus (retourné par `/healthz`)
```typescript
interface HealthStatus {
  status: "ok";
  tenants: string[];
  worker_count: number;
  queue_depth: number | null;
  oldest_pending_age_seconds: number | null;
  dead_count: number;          // NEW — triggers avec last_error LIKE 'DEAD:%'
}
```

### KanbanTrigger (triggers enrichis pour le Kanban)
```typescript
interface KanbanTrigger {
  id: string;
  tenant: string;
  source: string;
  external_id: string;
  received_at: string;         // ISO datetime
  claimed_at: string | null;
  claimed_by: string | null;
  attempts: number;
  last_error: string | null;
  mission_id: string | null;
}
```

### KanbanView (retourné par `/v1/missions/kanban`)
```typescript
interface KanbanView {
  en_attente: KanbanTrigger[];    // matched=true, claimed_at IS NULL, processed_at IS NULL
  reservee: KanbanTrigger[];      // claimed_at IS NOT NULL, processed_at IS NULL
  terminee: MissionSummary[];     // missions fermées dans les 24h
  en_echec: KanbanTrigger[];     // last_error LIKE 'DEAD:%', processed_at IS NULL
}
```

### MissionLifecycle (retourné par `/v1/missions/{id}/lifecycle`)
```typescript
interface MissionLifecycle {
  trigger_id: string | null;
  received_at: string | null;
  claimed_at: string | null;
  claimed_by: string | null;
  attempts: number;
  last_error: string | null;
  mission_created_at: string | null;
  mission_closed_at: string | null;
  mission_status: string;
}
```

### MetricsSnapshot (retourné par `/v1/metrics/snapshot`)
```typescript
interface MetricsSnapshot {
  queue_depth: number;
  queue_inflight: number;
  oldest_pending_age_seconds: number | null;
  mission_completed_24h: number;
  mission_dead_total: number;
  duration_p50_seconds: number | null;
  duration_p95_seconds: number | null;
  duration_p99_seconds: number | null;
  // Historique pour les graphiques (dernières 60 mesures)
  history: MetricsDataPoint[];
}

interface MetricsDataPoint {
  ts: string;                   // timestamp ISO
  depth: number;
  inflight: number;
}
```

**Note** : `history` est stocké en mémoire (liste circulaire côté back-end, max 60 points, 1 point toutes les 10s = 10 min de données). Alternative : `RingBuffer` en mémoire process (non persisté entre restarts).

### AgentCard (retourné par `/v1/admin/agents/catalog`)
```typescript
interface AgentCard {
  name: string;                  // depuis frontmatter SKILL.md
  agent_dir: string;             // nom du dossier (ex: "kafka_strimzi_expert")
  description: string;           // depuis frontmatter
  version: string;               // depuis frontmatter
  description_long: string;      // corps du SKILL.md (tronqué à 500 chars)
  active: boolean;               // toujours true pour les agents installés
}
```

### SkillCard (retourné par `/v1/admin/skills/catalog`)
```typescript
interface SkillCard {
  agent_name: string;
  agent_dir: string;
  category: "infrastructure" | "données" | "externe" | "autre";
  skills: string[];              // extraits du corps SKILL.md (sections ##, -bullets)
}
```

### RetryResult (retourné par `POST /v1/triggers/{id}/retry`)
```typescript
interface RetryResult {
  id: string;
  tenant: string;
  source: string;
  status: "retried";
}
```

---

## États du Kanban — Machine d'états Trigger

```
             ┌─────────────────────────────────────────────────────┐
             │                 TRIGGERS                             │
             │                                                      │
  received   │  matched=true           claimed_at IS NOT NULL      │
  ──────────►│  processed_at=NULL  ──► processed_at=NULL          │
             │  claimed_at=NULL        (worker en cours)           │
             │  ↕ COLONNE              ↕ COLONNE                   │
             │  "En attente"           "Réservée"                  │
             │       │                      │                       │
             │       │ claim_next()         │ mark_processed()      │
             │       ▼                      ▼                       │
             │  claimed_at=now()       processed_at=now()          │
             │  claimed_by=worker_id   ──► MISSIONS table          │
             │                         ↕ COLONNE "Terminée"       │
             │                              │                       │
             │                    mark_dead() si attempts ≥ MAX    │
             │                              ▼                       │
             │                    last_error='DEAD:...'            │
             │                    ↕ COLONNE "En échec"             │
             │                              │                       │
             │                    POST /retry                       │
             │                    attempts=0, claimed_at=NULL       │
             │                    ──► retour "En attente"          │
             └─────────────────────────────────────────────────────┘
```

---

## Historique métriques — Ring Buffer en mémoire

Le endpoint `/v1/metrics/snapshot` accumule un historique de points. Implémentation recommandée :

```python
from collections import deque
from datetime import datetime

_metrics_history: deque[dict] = deque(maxlen=60)  # 60 points × 10s = 10 min

async def _collect_metrics_point(session):
    stats = await queue_stats(session)
    _metrics_history.append({
        "ts": datetime.utcnow().isoformat(),
        "depth": stats["depth"] or 0,
        "inflight": stats["inflight"] or 0,
    })
```

Ce collecteur est appelé par le background task `_refresh_metrics` dans `api/main.py` (déjà en place, intervalle `METRICS_REFRESH_INTERVAL`). Il suffit de l'étendre pour pousser dans `_metrics_history`.
