# Plan d'Implémentation : Refonte UI inspirée Hermes-Workspace

**Branche** : `013-hermes-ui-refonte` | **Date** : 2026-06-15 | **Spec** : [spec.md](./spec.md)

## Résumé

Transformer le frontend `web/` (Next.js 14 + Marcel design system) en s'inspirant de hermes-workspace. Phase 1 : OpsStrip live (santé plateforme), vue Kanban missions (4 colonnes FR), surveillance Recharts sur `/metrics`. Phase 2 : catalogue Agents & Skills depuis `agents/*/SKILL.md`. Phase 3 : Cost ledger Langfuse (conditionnel). UI 100% en français, Marcel comme seule source de couleurs.

---

## Contexte Technique

**Langage/Version** : TypeScript 5.x (Next.js 14, React 18) + Python 3.11 (FastAPI, back-end)  
**Dépendances principales** :
- Front : `@marcel/web-components@0.5.1`, `@marcel/web-tokens@0.5.1`, `@tanstack/react-query@5.x`, `recharts@2.x` (à ajouter), `lucide-react`, `clsx`
- Back : `fastapi`, `sqlalchemy[asyncio]`, `prometheus_client`, `pyyaml` (pour lire les SKILL.md)

**Stockage** : PostgreSQL 17 (table `triggers` avec colonnes durable-queue ajoutées par spec-011)  
**Tests** : `pytest` (back-end, 170 tests passent), `tsc --noEmit` (front-end)  
**Plateforme cible** : Linux server Docker (Next.js SPA + FastAPI)  
**Type de projet** : Application web fullstack  
**Contraintes** : Marcel CSS tokens = source unique des couleurs · Recharts uniquement dans client components · Pas de DnD · Colonnes `claimed_at`/`claimed_by`/`attempts`/`last_error` accessibles via raw SQL (pas encore dans l'ORM `core/models.py`)

---

## Constitution Check

| Principe | Statut | Justification |
|---|---|---|
| §I Read-Only v0 | ✅ | "Relancer" est une action humaine explicite (bouton UI), pas un agent autonome |
| §II Mission Isolation | ✅ | Aucun nouvel agent ni tool call |
| §III Post Jira opt-in | ✅ | "Publier sur Jira" déjà opt-in, comportement conservé |
| §IV Eval suite | ✅ | Aucun nouvel agent ni tool — pas de nouveau eval case requis |
| §V Zero secret leakage | ✅ | Pas de nouveau logging de secrets |
| §VI Skills = SKILL.md | ✅ | Catalogue agents lit `agents/*/SKILL.md` — source de vérité respectée |
| §VII Agnostic by design | ✅ | Aucun hardcode Enterprise dans `core/` ou `agents/` |
| §VIII Incident filters = Postgres | ✅ | Non affecté |

---

## Structure du projet (fichiers concernés)

```text
specs/013-hermes-ui-refonte/
├── plan.md              # Ce fichier
├── spec.md              # Spécification fonctionnelle
├── research.md          # Décisions techniques (Marcel SSR, Recharts, Prometheus JSON, TanStack Query)
├── data-model.md        # KanbanView, HealthStatus, MetricsSnapshot, AgentCard, SkillCard
├── quickstart.md        # Scénarios de test end-to-end
├── contracts/
│   └── api-contracts.md # Contrats API (6 nouveaux endpoints) + contrats composants React
└── tasks.md             # Généré par /speckit.tasks

web/                                    # Front-end Next.js
├── marcel.d.ts                         # MODIFIER : +15 déclarations JSX Marcel
├── app/
│   ├── layout.tsx                      # MODIFIER : insérer OpsStrip + AttentionCard
│   ├── missions/
│   │   └── page.tsx                    # MODIFIER : ajouter toggle Table|Kanban via ?view=
│   ├── missions/[id]/
│   │   └── page.tsx                    # MODIFIER : bloc "Cycle de vie" + auto-refresh
│   ├── monitoring/
│   │   └── page.tsx                    # RÉÉCRIRE : Recharts + /v1/metrics/snapshot
│   ├── admin/
│   │   ├── agents/
│   │   │   └── page.tsx               # CRÉER (Phase 2)
│   │   └── skills/
│   │       └── page.tsx               # CRÉER (Phase 2)
│   └── cost/
│       └── page.tsx                   # CRÉER (Phase 3)
├── components/
│   ├── SideBar.tsx                    # MODIFIER : liens "Agents", "Compétences", "Coûts"
│   ├── OpsStrip.tsx                   # CRÉER
│   ├── AttentionCard.tsx              # CRÉER
│   ├── MissionsKanban.tsx             # CRÉER
│   ├── KanbanTriggerCard.tsx          # CRÉER
│   ├── MissionLifecycle.tsx           # CRÉER
│   └── MonitoringCharts.tsx           # CRÉER
└── lib/
    └── api.ts                         # MODIFIER : getHealthz, getMissionsKanban, getMissionLifecycle,
                                       #             getMetricsSnapshot, retryTrigger,
                                       #             getAgentsCatalog, getSkillsCatalog

api/                                   # Back-end FastAPI
├── main.py                            # MODIFIER : dead_count dans /healthz
├── routes/
│   ├── missions.py                    # MODIFIER : GET /v1/missions/kanban, GET /{id}/lifecycle
│   ├── triggers.py                    # MODIFIER : POST /{id}/retry
│   ├── metrics.py                     # MODIFIER : GET /v1/metrics/snapshot + ring buffer
│   └── admin.py                       # MODIFIER : GET /v1/admin/agents/catalog + /skills/catalog
└── schemas.py                         # MODIFIER : KanbanTrigger, KanbanView, MissionLifecycle,
                                       #             MetricsSnapshot, AgentCard, SkillCard, RetryResult

core/
└── models.py                          # MODIFIER : ajouter claimed_at/claimed_by/attempts/last_error
                                       #             au mapping SQLAlchemy Trigger (Phase 1)
```

---

## Phase 1 — Shell + Kanban + Monitoring (valeur immédiate)

### 1.1 Étendre `web/marcel.d.ts`

Ajouter ~15 déclarations JSX en suivant le pattern de `mrcl-button` déjà présent :
```typescript
declare namespace JSX {
  interface IntrinsicElements {
    "mrcl-modal": React.DetailedHTMLProps<...> & {
      open?: boolean;
      heading?: string;
    };
    "mrcl-drawer": React.DetailedHTMLProps<...> & {
      open?: boolean;
      position?: "left" | "right";
      heading?: string;
    };
    "mrcl-tabs": React.DetailedHTMLProps<...>;
    "mrcl-tab": React.DetailedHTMLProps<...> & { label?: string; };
    // ... etc.
  }
}
```

### 1.2 Ajouter `claimed_at`/`claimed_by`/`attempts`/`last_error` à `core/models.py:Trigger`

```python
# Dans class Trigger(Base):
claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
claimed_by: Mapped[str | None] = mapped_column(String, nullable=True)
attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
last_error: Mapped[str | None] = mapped_column(String, nullable=True)
```

Et ajouter les champs dans `api/schemas.py:TriggerResponse`.

### 1.3 Nouveaux schémas Pydantic (`api/schemas.py`)

```python
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

class KanbanView(BaseModel):
    en_attente: list[KanbanTrigger]
    reservee: list[KanbanTrigger]
    terminee: list[MissionSummary]
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

class MetricsSnapshot(BaseModel):
    queue_depth: int
    queue_inflight: int
    oldest_pending_age_seconds: float | None
    mission_completed_24h: int
    mission_dead_total: int
    duration_p50_seconds: float | None
    duration_p95_seconds: float | None
    duration_p99_seconds: float | None
    history: list[dict]

class RetryResult(BaseModel):
    id: str
    tenant: str
    source: str
    status: str = "retried"
```

### 1.4 Enrichir `/healthz` (`api/main.py`)

```python
# Ajouter à la query healthz :
from sqlalchemy import text

dead_q = text("SELECT count(*) FROM triggers WHERE last_error LIKE 'DEAD:%' AND processed_at IS NULL")
dead_count: int = (await session.execute(dead_q)).scalar_one()

return {
    "status": "ok",
    "tenants": ...,
    "worker_count": worker_count,
    "queue_depth": stats["depth"],
    "oldest_pending_age_seconds": stats["oldest_pending_age_seconds"],
    "dead_count": dead_count,   # NEW
}
```

### 1.5 Endpoint `GET /v1/missions/kanban` (`api/routes/missions.py`)

Utiliser ORM queries sur le modèle `Trigger` enrichi (après 1.2) :
```python
@router.get("/kanban", response_model=KanbanView)
async def missions_kanban(db: DB) -> KanbanView:
    # 4 requêtes parallèles avec asyncio.gather
    en_attente = select(Trigger).where(
        Trigger.matched.is_(True),
        Trigger.processed_at.is_(None),
        Trigger.claimed_at.is_(None),
    ).order_by(Trigger.received_at.asc()).limit(50)
    ...
```

### 1.6 Endpoint `GET /v1/missions/{id}/lifecycle` (`api/routes/missions.py`)

```python
@router.get("/{mission_id}/lifecycle", response_model=MissionLifecycle)
async def mission_lifecycle(mission_id: str, db: DB) -> MissionLifecycle:
    mission = await _get_or_404(db, mission_id)
    trigger = (await db.execute(
        select(Trigger).where(Trigger.mission_id == mission_id).limit(1)
    )).scalar_one_or_none()
    return MissionLifecycle(
        trigger_id=str(trigger.id) if trigger else None,
        received_at=trigger.received_at if trigger else None,
        claimed_at=trigger.claimed_at if trigger else None,
        claimed_by=trigger.claimed_by if trigger else None,
        attempts=trigger.attempts if trigger else 0,
        last_error=trigger.last_error if trigger else None,
        mission_created_at=mission.created_at,
        mission_closed_at=mission.closed_at,
        mission_status=mission.status,
    )
```

### 1.7 Endpoint `POST /v1/triggers/{id}/retry` (`api/routes/triggers.py`)

```python
@router.post("/{trigger_id}/retry", response_model=RetryResult)
async def retry_trigger(trigger_id: str, db: DB) -> RetryResult:
    trigger = (await db.execute(
        select(Trigger).where(Trigger.id == trigger_id)
    )).scalar_one_or_none()
    if not trigger:
        raise HTTPException(404, f"Trigger not found: {trigger_id}")
    if not (trigger.last_error or "").startswith("DEAD:"):
        raise HTTPException(409, "Trigger is not in DEAD state")
    if trigger.processed_at is not None:
        raise HTTPException(409, "Trigger already processed")
    
    trigger.last_error = None
    trigger.claimed_at = None
    trigger.claimed_by = None
    trigger.attempts = 0
    db.add(SystemAudit(action="RETRY_TRIGGER", resource_type="TRIGGER", resource_id=trigger_id))
    await db.commit()
    return RetryResult(id=trigger_id, tenant=trigger.tenant, source=trigger.source)
```

### 1.8 Ring buffer + Endpoint `GET /v1/metrics/snapshot` (`api/routes/metrics.py`)

```python
from collections import deque
_history: deque[dict] = deque(maxlen=60)

def push_history_point(depth: int, inflight: int) -> None:
    _history.append({"ts": datetime.utcnow().isoformat(), "depth": depth, "inflight": inflight})

@router.get("/v1/metrics/snapshot")
async def metrics_snapshot(db: DB) -> MetricsSnapshot:
    stats = await queue_stats(db)
    # percentiles via SQL
    pct_row = (await db.execute(text("""
        SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM (closed_at - created_at))),
               percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM (closed_at - created_at))),
               percentile_cont(0.99) WITHIN GROUP (ORDER BY extract(epoch FROM (closed_at - created_at)))
        FROM missions WHERE closed_at > now() - interval '1 hour' AND closed_at IS NOT NULL
    """))).fetchone()
    completed_24h = (await db.execute(text(
        "SELECT count(*) FROM missions WHERE closed_at > now() - interval '24 hours'"
    ))).scalar_one()
    dead_total = (await db.execute(text(
        "SELECT count(*) FROM triggers WHERE last_error LIKE 'DEAD:%' AND processed_at IS NULL"
    ))).scalar_one()
    
    return MetricsSnapshot(
        queue_depth=stats["depth"] or 0,
        queue_inflight=stats["inflight"] or 0,
        oldest_pending_age_seconds=stats["oldest_pending_age_seconds"],
        mission_completed_24h=completed_24h,
        mission_dead_total=dead_total,
        duration_p50_seconds=pct_row[0] if pct_row else None,
        duration_p95_seconds=pct_row[1] if pct_row else None,
        duration_p99_seconds=pct_row[2] if pct_row else None,
        history=list(_history),
    )
```

`push_history_point()` est appelé depuis `_refresh_metrics` dans `api/main.py`.

### 1.9 Composants React

**`web/components/OpsStrip.tsx`** (client component) :
```tsx
"use client";
import { useQuery } from "@tanstack/react-query";
import { getHealthz } from "@/lib/api";

export function OpsStrip() {
  const { data } = useQuery({ queryKey: ["healthz"], queryFn: getHealthz, refetchInterval: 5_000 });
  const status = !data ? "loading"
    : data.dead_count >= 1 || (data.oldest_pending_age_seconds || 0) > 600 ? "critique"
    : data.queue_depth > 50 ? "attention"
    : "ok";
  // Affichage Marcel tokens + mrcl-tag
}
```

**`web/components/AttentionCard.tsx`** : reçoit `health` prop, s'affiche si `status !== "ok"`.

**`web/components/MissionsKanban.tsx`** : 4 colonnes, chaque colonne = liste de cartes, auto-refresh 8s.

**`web/components/KanbanTriggerCard.tsx`** : carte individuelle avec bouton "Relancer" conditionnel.

**`web/app/missions/page.tsx`** : ajouter `?view=table|kanban`, toggle buttons, rendre `<MissionsKanban>` conditionnel.

**`web/app/missions/[id]/page.tsx`** : ajouter `<MissionLifecycle missionId={...} />`, auto-refresh via TanStack Query.

**`web/app/monitoring/page.tsx`** : remplacer les 4 StatCards antipattern par `<MonitoringCharts>` (Recharts) + conserver le journal d'activité.

**`web/app/layout.tsx`** : insérer `<OpsStrip />` et `<AttentionCard />` dans le shell :
```tsx
<main className="flex-1 flex flex-col min-w-0 h-screen overflow-y-auto">
  <OpsStrip />                  {/* NEW */}
  <AttentionCard />             {/* NEW — conditionnel */}
  <div className="p-8 max-w-[1600px] w-full mx-auto">
    {children}
  </div>
</main>
```

---

## Phase 2 — Catalogues Agents & Skills

### 2.1 Endpoint `GET /v1/admin/agents/catalog` (`api/routes/admin.py`)

```python
import yaml
from pathlib import Path

AGENTS_DIR = Path(__file__).parent.parent.parent / "agents"

@router.get("/agents/catalog", response_model=list[AgentCard])
async def agents_catalog() -> list[AgentCard]:
    result = []
    for skill_file in sorted(AGENTS_DIR.glob("*/SKILL.md")):
        text = skill_file.read_text(encoding="utf-8")
        if text.startswith("---"):
            _, front, body = text.split("---", 2)
            meta = yaml.safe_load(front)
            result.append(AgentCard(
                name=meta.get("name", skill_file.parent.name),
                agent_dir=skill_file.parent.name,
                description=meta.get("description", "").strip()[:200],
                version=str(meta.get("version", "1.0")),
                description_long=body.strip()[:500],
                active=True,
            ))
    return result
```

### 2.2 Endpoint `GET /v1/admin/skills/catalog` (même fichier)

Parse chaque SKILL.md, extrait les skills depuis le corps (sections `##` + bullet points `-`).

### 2.3 Pages Next.js (Phase 2)

- `web/app/admin/agents/page.tsx` : grille 3 colonnes de `AgentCard` (mrcl-card style)
- `web/app/admin/skills/page.tsx` : liste filtrable avec `mrcl-combobox` pour filtre catégorie
- `web/components/SideBar.tsx` : ajouter liens "Agents" et "Compétences" sous "Administration"

---

## Phase 3 — Cost Ledger (conditionnel, après validation Langfuse)

- `api/routes/cost.py` : `GET /v1/cost/aggregate` — proxy Langfuse REST (`/api/public/traces` + `usage` fields)
- `web/app/cost/page.tsx` : tableau + Recharts area chart 7j
- `web/components/SideBar.tsx` : ajouter lien "Coûts"

**Pré-requis** : validation que Langfuse self-hosted expose `/api/public/traces` avec `usage.totalTokens` et `usage.totalCost`.

---

## Dépendances à ajouter

```bash
cd web
pnpm add recharts          # v2.x, ~50 kB gz, MIT
pnpm add -D @types/recharts  # si non inclus
```

```python
# api — déjà disponibles : pyyaml (pour SKILL.md parsing)
# vérifier dans pyproject.toml : pyyaml doit être listée
```

---

## Ordre d'implémentation recommandé

```
T001-T005  : Fondations (marcel.d.ts, ORM Trigger, schemas Pydantic)
T006-T010  : Endpoints back-end Phase 1 (healthz, kanban, lifecycle, retry, snapshot)
T011-T015  : Composants front Phase 1 (OpsStrip, AttentionCard, lib/api.ts)
T016-T020  : Kanban (MissionsKanban, KanbanTriggerCard, page missions toggle)
T021-T025  : Mission detail + Monitoring (lifecycle page, monitoring rewrite)
T026-T030  : Phase 2 Agents/Skills (endpoints + pages)
T031+      : Phase 3 Cost (optionnel)
```

---

## Critères de validation technique

```bash
# 1. TypeScript
cd web && npx tsc --noEmit         # 0 erreur attendue

# 2. Build production
cd web && pnpm build               # 0 erreur build

# 3. Tests back-end non-régression
uv run pytest tests/unit/ -q       # 170 passed attendus

# 4. OpsStrip live
curl http://localhost:8000/healthz | jq .dead_count   # nombre entier

# 5. Kanban
curl http://localhost:8000/v1/missions/kanban | jq 'keys'
# → ["en_attente", "en_echec", "reservee", "terminee"]

# 6. Retry trigger (avec un trigger DEAD en DB)
curl -X POST http://localhost:8000/v1/triggers/<uuid>/retry
# → {"status": "retried", ...}

# 7. Metrics snapshot
curl http://localhost:8000/v1/metrics/snapshot | jq .queue_depth  # nombre

# 8. Agents catalog
curl http://localhost:8000/v1/admin/agents/catalog | jq '. | length'  # 6
```
