# Recherche Technique — 013-hermes-ui-refonte

## 1. Marcel Stencil Web Components + React / Next.js 14 App Router

**Décision** : Utiliser le pattern `"use client"` + `defineCustomElements()` déjà établi dans `app/marcel-provider.tsx`. Tout nouveau composant utilisant des éléments `mrcl-*` doit être un client component.

**Rationale** : Les web components Stencil accèdent aux APIs navigateur (DOM, `customElements.define`). Ils ne peuvent pas s'hydrater côté serveur dans Next.js App Router. `MarcelProvider` appelle déjà `defineCustomElements()` dans un `useEffect`, ce qui initialise tous les custom elements une seule fois au montage. Les nouvelles cartes (OpsStrip, KanbanCard, etc.) héritent de cette initialisation.

**Pattern concret** :
```tsx
// Tout composant qui utilise mrcl-* doit commencer par :
"use client";
// Pas besoin de dynamic import — defineCustomElements() est déjà appelé par MarcelProvider
```

**Déclarations JSX manquantes** : `web/marcel.d.ts` ne déclare que 3 composants. Il faut ajouter les déclarations pour `mrcl-modal`, `mrcl-drawer`, `mrcl-tabs`, `mrcl-input-text`, `mrcl-select`, `mrcl-combobox`, `mrcl-textarea`, `mrcl-toaster`, `mrcl-toaster-container`, `mrcl-spinner`, `mrcl-skeleton`, `mrcl-popover`, `mrcl-checkbox`, `mrcl-toggle`. Modèle à suivre : déclaration existante de `mrcl-button` dans `web/marcel.d.ts`.

**Alternatives considérées** : `@stencil/react-output-target` (wrappers React natifs) — trop lourd pour notre setup, non nécessaire.

---

## 2. Recharts + Next.js 14 App Router

**Décision** : Utiliser Recharts directement dans les composants `"use client"`. Pas de `dynamic(() => import(...), { ssr: false })` nécessaire — `app/monitoring/page.tsx` sera entièrement client-side.

**Rationale** : Recharts utilise `window` et `ResizeObserver`. Ces APIs sont disponibles dans les client components. Puisque `monitoring/page.tsx` est déjà `"use client"` (il utilise `useEffect`), importer Recharts directement ne cause pas d'erreur SSR. Version recommandée : `recharts@2.x` (stable, MIT, ~50 kB gz).

**Installation** : `pnpm add recharts` dans `web/`.

**Pattern concret** :
```tsx
"use client";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
// Use Marcel CSS tokens for colors:
const COLOR_PRIMARY = "var(--mrcl-persistent-content-default)";
const COLOR_ACCENT = "var(--crf-blue)";
```

**Alternatives considérées** : ECharts (~300 kB gz) — trop lourd. D3 — trop bas niveau. Sparklines SVG maison — pas assez expressif pour les histogrammes.

---

## 3. Endpoint `/v1/metrics/snapshot` — Stratégie d'exposition

**Décision** : Le endpoint `/v1/metrics/snapshot` interroge directement la base de données et les métriques en mémoire (prometheus_client singletons) via leur interface Python publique, et retourne un JSON typé. Il ne parse pas le format texte Prometheus.

**Rationale** : Parser `generate_latest()` (texte Prometheus) côté back-end ou front-end est fragile et non nécessaire. Les métriques Prometheus `Gauge` et `Counter` exposent `._value.get()` / `._metrics` mais ces attributs sont privés. La meilleure approche : utiliser `queue_stats()` (déjà disponible dans `agents/pipeline/durable_queue.py`) pour les métriques DB, et interroger les singletons Prometheus via `REGISTRY.get_sample_value()` pour les counters/histogrammes.

**Pattern concret** :
```python
from prometheus_client import REGISTRY

@router.get("/v1/metrics/snapshot")
async def metrics_snapshot(db: DB):
    stats = await queue_stats(db)  # depth, inflight, oldest_pending_age_seconds
    
    # Counters via REGISTRY
    completed = REGISTRY.get_sample_value("kafkaops_mission_completed_total") or 0
    dead = REGISTRY.get_sample_value("kafkaops_mission_dead_total") or 0
    
    # Histogram quantiles
    p50 = REGISTRY.get_sample_value("kafkaops_mission_duration_seconds", {"quantile": "0.5"}) or 0
    p95 = REGISTRY.get_sample_value("kafkaops_mission_duration_seconds", {"quantile": "0.95"}) or 0
    
    return MetricsSnapshot(queue_depth=stats["depth"], ...)
```

**Limitations** : Les histogrammes Prometheus standard n'exposent pas les quantiles nativement (seulement les buckets). Pour les quantiles, il faut soit (a) changer vers `Summary` plutôt que `Histogram`, soit (b) calculer les percentiles depuis la DB directement sur les `missions` clôturées. **Decision** : garder `Histogram` pour Grafana/Prometheus externe, calculer les percentiles dans le snapshot endpoint via `percentile_cont` PostgreSQL.

**SQL quantile** :
```sql
SELECT 
    percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM (closed_at - created_at))) AS p50,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM (closed_at - created_at))) AS p95,
    percentile_cont(0.99) WITHIN GROUP (ORDER BY extract(epoch FROM (closed_at - created_at))) AS p99
FROM missions 
WHERE closed_at > now() - interval '1 hour'
AND closed_at IS NOT NULL;
```

---

## 4. TanStack Query — Pattern de polling dans App Router

**Décision** : Utiliser `useQuery` avec `refetchInterval` pour tous les composants client qui pollient le back-end. La configuration `QueryClient` est déjà en place dans `app/providers.tsx` (staleTime: 30s, retry: 1).

**Rationale** : `app/providers.tsx` expose déjà `QueryClientProvider`. Les composants server n'ont pas accès à TanStack Query — ce qui est correct : `OpsStrip`, `MissionsKanban`, et le monitoring chart sont tous des client components.

**Pattern concret** :
```tsx
"use client";
import { useQuery } from "@tanstack/react-query";

const { data: health } = useQuery({
  queryKey: ["healthz"],
  queryFn: getHealthz,
  refetchInterval: 5_000,   // 5s pour OpsStrip
  staleTime: 2_000,
});
```

**Valeurs de polling par composant** :
| Composant | `refetchInterval` | Justification |
|---|---|---|
| OpsStrip | 5 000 ms | Santé globale — fréquence raisonnable |
| AttentionCard | même query que OpsStrip | Partage le cache TanStack |
| MissionsKanban | 8 000 ms | Idem que l'actuel monitoring |
| MissionLifecycle | 3 000 ms | Mission en cours — mise à jour rapide |
| Monitoring charts | 10 000 ms | Graphiques — pas besoin de sub-10s |

---

## 5. Catalogue Agents & Skills — Source (constitution §VI)

**Décision** : Le catalogue des agents lit les fichiers `agents/*/SKILL.md` (frontmatter YAML). Ces fichiers sont la source de vérité per constitution §VI. L'endpoint `/v1/admin/agents/catalog` lit ces fichiers au démarrage et expose leur contenu.

**Agents trouvés** (par `agents/*/SKILL.md`) :
- `agents/intake/SKILL.md` — intake-agent (classification, extraction)
- `agents/kafka_strimzi_expert/SKILL.md` — kafka expert
- `agents/k8s_gcp_sre/SKILL.md` — k8s/GCP SRE expert
- `agents/prom_alerts_triage/SKILL.md` — alertes Prometheus
- `agents/evidence_consolidator/SKILL.md` — consolidation preuves
- `agents/post_mortem_analyst/SKILL.md` — capitalisation post-incident

**Frontmatter format** (exemple `agents/intake/SKILL.md`) :
```yaml
---
name: intake-agent
description: Parse incoming trigger payload, extract env/cluster/type/subject
version: "1.0"
---
```

**Pattern d'implémentation** :
```python
import yaml
from pathlib import Path

def scan_agents_catalog(agents_dir: Path) -> list[dict]:
    result = []
    for skill_file in agents_dir.glob("*/SKILL.md"):
        text = skill_file.read_text()
        if text.startswith("---"):
            _, front, body = text.split("---", 2)
            meta = yaml.safe_load(front)
            result.append({"agent_dir": skill_file.parent.name, **meta, "description_long": body.strip()[:500]})
    return result
```

**Alternatives considérées** : Introspection Python des classes Agent (import + inspect) — fragile, dépend de l'ordre d'import. Base de données — interdit par constitution §VI. Hardcode en config YAML — viole constitution §VII (Agnostic by design).

---

## 6. Kanban — Colonnes depuis triggers durable queue

**Décision** : Le endpoint `/v1/missions/kanban` utilise du SQL brut (comme `durable_queue.py`) pour lire les colonnes `claimed_at`, `claimed_by`, `last_error` qui ont été ajoutées par la migration Alembic spec-011, mais ne sont PAS encore dans le modèle SQLAlchemy `core/models.py:Trigger`.

**Rationale** : L'ORM `Trigger` n'a pas ces colonnes dans son mapping Python. Plutôt que de modifier `core/models.py` maintenant (scope creep), on utilise `text()` SQLAlchemy pour les nouvelles colonnes, cohérent avec `durable_queue.py`. Une tâche de spec-013 ajoutera les colonnes au modèle ORM pour cohérence.

**Colonnes Kanban** :
- `en_attente` : `matched=true AND processed_at IS NULL AND claimed_at IS NULL`
- `reservee` : `matched=true AND processed_at IS NULL AND claimed_at IS NOT NULL`
- `terminee` : missions `closed_at > now() - interval '24h'` (query sur table `missions`)
- `en_echec` : `last_error LIKE 'DEAD:%' AND processed_at IS NULL`

**Schéma retourné** :
```python
class KanbanTrigger(BaseModel):
    id: str
    tenant: str
    source: str
    external_id: str
    received_at: datetime
    claimed_at: datetime | None
    claimed_by: str | None
    attempts: int
    last_error: str | None
    mission_id: str | None

class KanbanView(BaseModel):
    en_attente: list[KanbanTrigger]
    reservee: list[KanbanTrigger]
    terminee: list[MissionSummary]  # type existant
    en_echec: list[KanbanTrigger]
```

---

## 7. Endpoint Retry — `/v1/triggers/{id}/retry`

**Décision** : Le endpoint remet un trigger "DEAD" dans la file durable en resetant `last_error=NULL`, `claimed_at=NULL`, `attempts=0`. Idempotent : renvoie 404 si le trigger n'existe pas, 409 si `last_error NOT LIKE 'DEAD:%'` (pas en état d'échec terminal).

**Audit** : Chaque retry est logué dans `system_audit` (action=`RETRY_TRIGGER`, resource_type=`TRIGGER`).

**Pattern SQL** :
```sql
UPDATE triggers 
SET last_error = NULL, claimed_at = NULL, claimed_by = NULL, attempts = 0
WHERE id = :id AND last_error LIKE 'DEAD:%'
RETURNING id, tenant, source, external_id
```

---

## 8. Colorimétrie — Marcel tokens vs Tailwind

**Décision** : Toutes les couleurs sémantiques doivent utiliser les CSS custom properties Marcel (`var(--mrcl-persistent-*)`). Les couleurs Tailwind codées en dur (`bg-slate-950`, `text-blue-400`) dans le code existant sont conservées telles quelles pour éviter une régression de style. Les nouveaux composants (OpsStrip, Kanban, etc.) utilisent exclusivement les tokens Marcel.

**Tokens principaux** (depuis `web/app/globals.css`) :
| Token | Usage |
|---|---|
| `--mrcl-persistent-background-default` | Fond principal |
| `--mrcl-persistent-background-subtle` | Fond carte/panel |
| `--mrcl-persistent-border-default` | Bordure |
| `--mrcl-persistent-content-default` | Texte principal |
| `--mrcl-persistent-content-subtle` | Texte secondaire |
| `--crf-blue` | Couleur accent Carrefour (#003087) |

**Palette Kanban (via mrcl-tag)** :
- En attente : `mrcl-tag variant="info"`
- Réservée : `mrcl-tag variant="warning"`
- Terminée : `mrcl-tag variant="success"`
- En échec : `mrcl-tag variant="error"`
