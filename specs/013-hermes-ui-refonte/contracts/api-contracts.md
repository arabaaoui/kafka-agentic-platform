# Contrats d'Interface API — 013-hermes-ui-refonte

## Contrats Back-End (nouveaux endpoints)

### GET /healthz — Enrichissement (existant, à étendre)

**Fichier** : `api/main.py` — fonction `healthz()`

**Réponse actuelle** :
```json
{
  "status": "ok",
  "tenants": ["enterprise"],
  "worker_count": 2,
  "queue_depth": 5,
  "oldest_pending_age_seconds": 45.2
}
```

**Réponse cible** :
```json
{
  "status": "ok",
  "tenants": ["enterprise"],
  "worker_count": 2,
  "queue_depth": 5,
  "oldest_pending_age_seconds": 45.2,
  "dead_count": 1
}
```

**Nouveau champ** : `dead_count` (int) — `SELECT count(*) FROM triggers WHERE last_error LIKE 'DEAD:%' AND processed_at IS NULL`

---

### GET /v1/missions/kanban

**Fichier** : `api/routes/missions.py`

**Description** : Retourne les 4 colonnes Kanban en une seule requête. Limites : 50 par colonne (suffisant pour affichage).

**Requête** : `GET /v1/missions/kanban`

**Réponse 200** :
```json
{
  "en_attente": [
    {
      "id": "uuid",
      "tenant": "enterprise",
      "source": "alertmanager",
      "external_id": "alert-123",
      "received_at": "2026-06-15T10:00:00Z",
      "claimed_at": null,
      "claimed_by": null,
      "attempts": 0,
      "last_error": null,
      "mission_id": null
    }
  ],
  "reservee": [ /* même structure, claimed_at != null */ ],
  "terminee": [
    {
      "mission_id": "MSN-2026-001",
      "tenant": "enterprise",
      "env": "PROD",
      "subject": "pvc-saturation",
      "status": "CLOSED",
      "created_at": "2026-06-15T10:00:00Z",
      "closed_at": "2026-06-15T10:15:00Z"
    }
  ],
  "en_echec": [ /* KanbanTrigger avec last_error LIKE 'DEAD:%' */ ]
}
```

**Logique SQL** (utilise raw `text()` pour les colonnes durable queue) :
```sql
-- en_attente
SELECT id, tenant, source, external_id, received_at, 
       claimed_at, claimed_by, attempts, last_error, mission_id
FROM triggers
WHERE matched = true AND processed_at IS NULL AND claimed_at IS NULL
ORDER BY received_at ASC LIMIT 50;

-- reservee
SELECT ... WHERE matched = true AND processed_at IS NULL AND claimed_at IS NOT NULL
ORDER BY claimed_at ASC LIMIT 50;

-- terminee
SELECT mission_id, tenant, env, subject, status, created_at, closed_at
FROM missions WHERE closed_at > now() - interval '24 hours'
ORDER BY closed_at DESC LIMIT 50;

-- en_echec
SELECT ... WHERE last_error LIKE 'DEAD:%' AND processed_at IS NULL
ORDER BY received_at ASC LIMIT 50;
```

---

### GET /v1/missions/{mission_id}/lifecycle

**Fichier** : `api/routes/missions.py`

**Description** : Retourne le cycle de vie complet d'une mission — données trigger (durable queue) + données mission.

**Réponse 200** :
```json
{
  "trigger_id": "uuid",
  "received_at": "2026-06-15T10:00:00Z",
  "claimed_at": "2026-06-15T10:00:02Z",
  "claimed_by": "worker-12345-0",
  "attempts": 1,
  "last_error": null,
  "mission_created_at": "2026-06-15T10:00:05Z",
  "mission_closed_at": "2026-06-15T10:15:30Z",
  "mission_status": "CLOSED"
}
```

**Réponse 404** : mission non trouvée  
**Réponse 200 sans trigger** : `trigger_id: null`, champs trigger à null (si la mission a été créée hors-trigger).

---

### POST /v1/triggers/{trigger_id}/retry

**Fichier** : `api/routes/triggers.py`

**Description** : Remet un trigger DEAD dans la file durable. Action explicite humaine (constitution §I — pas un agent autonome).

**Réponse 200** :
```json
{
  "id": "uuid",
  "tenant": "enterprise",
  "source": "alertmanager",
  "status": "retried"
}
```

**Réponse 404** : trigger non trouvé  
**Réponse 409** : trigger pas en état DEAD (last_error NOT LIKE 'DEAD:%')  
**Réponse 409** : trigger déjà traité (processed_at IS NOT NULL)

**Effet** : UPDATE triggers SET last_error=NULL, claimed_at=NULL, claimed_by=NULL, attempts=0  
**Audit** : INSERT system_audit (action='RETRY_TRIGGER', resource_type='TRIGGER', resource_id=trigger_id)

---

### GET /v1/metrics/snapshot

**Fichier** : `api/routes/metrics.py`

**Description** : Métriques plateforme sous forme JSON pour la page Surveillance (pas le format texte Prometheus).

**Réponse 200** :
```json
{
  "queue_depth": 5,
  "queue_inflight": 2,
  "oldest_pending_age_seconds": 45.2,
  "mission_completed_24h": 42,
  "mission_dead_total": 1,
  "duration_p50_seconds": 120.5,
  "duration_p95_seconds": 285.0,
  "duration_p99_seconds": 450.0,
  "history": [
    { "ts": "2026-06-15T10:00:00Z", "depth": 3, "inflight": 1 },
    { "ts": "2026-06-15T10:00:10Z", "depth": 4, "inflight": 2 }
  ]
}
```

**Sources** :
- `queue_depth`, `queue_inflight`, `oldest_pending_age_seconds` : `queue_stats()` depuis `durable_queue.py`
- `mission_completed_24h` : `SELECT count(*) FROM missions WHERE closed_at > now() - interval '24h'`
- `mission_dead_total` : `SELECT count(*) FROM triggers WHERE last_error LIKE 'DEAD:%' AND processed_at IS NULL`
- `duration_p50/p95/p99` : `percentile_cont()` sur `missions.closed_at - missions.created_at` dernière heure
- `history` : ring buffer en mémoire (60 points, 1 toutes les `METRICS_REFRESH_INTERVAL` secondes)

---

### GET /v1/admin/agents/catalog

**Fichier** : `api/routes/admin.py`

**Description** : Catalogue des agents actifs lus depuis `agents/*/SKILL.md`.

**Réponse 200** :
```json
[
  {
    "name": "intake-agent",
    "agent_dir": "intake",
    "description": "Parse incoming trigger payload (Jira issue or alertmanager alert)...",
    "version": "1.0",
    "description_long": "# Intake Agent — Trigger Analysis...",
    "active": true
  },
  {
    "name": "kafka-strimzi-expert",
    "agent_dir": "kafka_strimzi_expert",
    "description": "...",
    "version": "1.0",
    "description_long": "...",
    "active": true
  }
]
```

**Source** : glob `agents/*/SKILL.md`, parse frontmatter YAML

---

### GET /v1/admin/skills/catalog

**Fichier** : `api/routes/admin.py`

**Description** : Catalogue des compétences extraites des SKILL.md.

**Réponse 200** :
```json
[
  {
    "agent_name": "intake-agent",
    "agent_dir": "intake",
    "category": "autre",
    "skills": ["Parse Jira payloads", "Extract env/cluster/type/subject", "Classify INCIDENT vs INVESTIGATION"]
  }
]
```

**Catégories** (déduites du nom ou du contenu SKILL.md) :
- `infrastructure` : agents k8s, GCP, SRE
- `données` : agents Kafka, Prometheus
- `externe` : agents qui parlent à Jira, Care, etc.
- `autre` : intake, evidence consolidator, post mortem

---

## Contrats Front-End (composants React)

### OpsStrip

```typescript
interface OpsStripProps {
  // Pas de props — fetch en autonomie via useQuery
}
// Données depuis GET /healthz
// Affiche : worker_count, queue_depth, oldest_pending (formaté), dead_count, badge statut global
// Statut : "Opérationnel" (vert) / "Attention" (orange) / "Critique" (rouge)
```

### AttentionCard

```typescript
interface AttentionCardProps {
  health: HealthStatus;  // passé depuis OpsStrip
}
// Visible si : health.dead_count >= 1 || health.queue_depth > 50 || health.oldest_pending_age_seconds > 600
// Affiche le motif et des liens vers /missions?view=kanban
```

### MissionsKanban

```typescript
interface MissionsKanbanProps {
  // Pas de props — fetch en autonomie via useQuery
}
// Données depuis GET /v1/missions/kanban
// 4 colonnes : "En attente" | "Réservée" | "Terminée" | "En échec"
// Chaque carte : KanbanTriggerCard | MissionCard (colonne Terminée)
// Action Relancer : disponible uniquement sur les cartes "En échec"
```

### KanbanTriggerCard

```typescript
interface KanbanTriggerCardProps {
  item: KanbanTrigger;
  column: "en_attente" | "reservee" | "en_echec";
  onRetry?: (triggerId: string) => void;  // undefined sauf colonne en_echec
}
// Affiche : source, tenant, received_at (relatif), attempts, claimed_by (si reservee), last_error snippet
```

### MissionLifecycle

```typescript
interface MissionLifecycleProps {
  missionId: string;
}
// Données depuis GET /v1/missions/{id}/lifecycle
// Frise chronologique : Reçu → Réservé → Mission créée → Traité
// Chaque étape : timestamp formaté + durée depuis étape précédente
// Si étape manquante (null) : affichée en grisé
```

### MonitoringCharts

```typescript
interface MonitoringChartsProps {
  // Pas de props — fetch en autonomie
}
// Données depuis GET /v1/metrics/snapshot
// Chart 1 (Line) : history.depth + history.inflight (axe temps)
// Chart 2 (Bar) : [p50, p95, p99] duration_seconds
// Chart 3 (Pie) : completed_24h vs dead_total
```
