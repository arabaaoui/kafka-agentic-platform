# Tasks: Refonte UI inspirée Hermes-Workspace

**Input**: Design documents from `/specs/013-hermes-ui-refonte/`  
**Branch**: `013-hermes-ui-refonte`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Organisation** : Tâches groupées par histoire utilisateur pour une livraison incrémentale indépendante.

## Format : `[ID] [P?] [Story] Description`

- **[P]** : Peut s'exécuter en parallèle (fichiers différents, pas de dépendance)
- **[Story]** : Histoire utilisateur correspondante (US1…US6)
- Chemins de fichiers absolus depuis la racine du dépôt

---

## Phase 1 : Setup (Infrastructure partagée)

**Objectif** : Ajouter les dépendances manquantes avant tout développement.

- [X] T001 Ajouter `recharts@2.x` dans `web/package.json` via `cd web && pnpm add recharts`
- [X] T002 Vérifier que `pyyaml` est listé dans `pyproject.toml` (ajouter avec `uv add pyyaml` si absent)

---

## Phase 2 : Fondations (Prérequis bloquants)

**Objectif** : Socle commun que toutes les histoires utilisateur partagent.

**⚠️ CRITIQUE** : Aucune histoire utilisateur ne peut démarrer avant que cette phase soit terminée.

- [X] T003 [P] Étendre `web/marcel.d.ts` avec ~15 déclarations JSX Marcel manquantes : `mrcl-modal`, `mrcl-drawer`, `mrcl-tabs`, `mrcl-tab`, `mrcl-input-text`, `mrcl-input-number`, `mrcl-select`, `mrcl-combobox`, `mrcl-textarea`, `mrcl-toaster`, `mrcl-toaster-container`, `mrcl-spinner`, `mrcl-skeleton`, `mrcl-popover`, `mrcl-checkbox`, `mrcl-toggle` — suivre le pattern existant de `mrcl-button` dans `web/marcel.d.ts`
- [X] T004 [P] Ajouter les colonnes durable-queue au mapping SQLAlchemy dans `core/models.py` : `claimed_at: Mapped[datetime | None]`, `claimed_by: Mapped[str | None]`, `attempts: Mapped[int]`, `last_error: Mapped[str | None]` — et ajouter ces champs dans `api/schemas.py:TriggerResponse`
- [X] T005 Ajouter les schémas Pydantic dans `api/schemas.py` : `KanbanTrigger`, `KanbanView`, `MissionLifecycle`, `MetricsSnapshot`, `RetryResult`, `AgentCard`, `SkillCard` — extraits de `specs/013-hermes-ui-refonte/data-model.md` (dépend de T004)
- [X] T006 [P] Ajouter les fonctions API clientes dans `web/lib/api.ts` : `getHealthz`, `getMissionsKanban`, `retryTrigger`, `getMissionLifecycle`, `getMetricsSnapshot`, `getAgentsCatalog`, `getSkillsCatalog` — suivre le pattern SSR/client (BASE_URL) existant dans `web/lib/api.ts`

**Checkpoint** : Fondations prêtes — les histoires utilisateur peuvent démarrer.

---

## Phase 3 : Histoire Utilisateur 1 — Tableau de bord opérationnel (Priorité : P1) 🎯 MVP

**Objectif** : OpsStrip visible sur toutes les pages + AttentionCard conditionnelle.

**Test indépendant** : Ouvrir l'application, vérifier que la barre de statut affiche `worker_count`, `queue_depth`, et un badge de santé. Forcer `last_error='DEAD:test'` sur un trigger en DB → AttentionCard apparaît en moins de 10s.

### Implémentation US1

- [X] T007 [US1] Enrichir `/healthz` avec `dead_count` dans `api/main.py` : ajouter `SELECT count(*) FROM triggers WHERE last_error LIKE 'DEAD:%' AND processed_at IS NULL` et inclure le résultat dans le dict retourné (dépend de T005)
- [X] T008 [P] [US1] Créer `web/components/OpsStrip.tsx` : composant client `"use client"`, `useQuery({ queryKey: ["healthz"], queryFn: getHealthz, refetchInterval: 5_000 })`, affiche `worker_count`, `queue_depth`, `oldest_pending_age_seconds` formaté, `dead_count`, badge `mrcl-tag` (variant `success`/`warning`/`critical`) selon seuils (dead≥1 ou oldest>600s → critique, depth>50 → attention)
- [X] T009 [P] [US1] Créer `web/components/AttentionCard.tsx` : composant client, reçoit `health` prop depuis l'état partagé TanStack Query `["healthz"]`, s'affiche si `dead_count >= 1 || queue_depth > 50 || oldest_pending_age_seconds > 600`, affiche motif en français + lien vers `/missions?view=kanban`
- [X] T010 [US1] Modifier `web/app/layout.tsx` pour insérer `<OpsStrip />` et `<AttentionCard />` à l'intérieur de `<main>` avant le `<div className="p-8 ...">` — les deux composants partagent la query `["healthz"]` via TanStack Query cache (dépend de T008, T009)

**Checkpoint** : US1 complète et testable indépendamment.

---

## Phase 4 : Histoire Utilisateur 2 — Vue Kanban des missions (Priorité : P2)

**Objectif** : Toggle Table/Kanban sur la page Missions, 4 colonnes FR, action "Relancer".

**Test indépendant** : Naviguer vers `/missions?view=kanban`, vérifier 4 colonnes. Insérer triggers de test (fixtures quickstart.md scénario 2), relancer depuis "En échec" → migration vers "En attente".

### Implémentation US2

- [X] T011 [P] [US2] Ajouter l'endpoint `GET /v1/missions/kanban` dans `api/routes/missions.py` : 4 requêtes via `asyncio.gather` sur le modèle `Trigger` enrichi (T004), retourne `KanbanView` (T005) — colonnes : `en_attente` (matched=true, claimed_at IS NULL, processed_at IS NULL), `reservee` (claimed_at IS NOT NULL, processed_at IS NULL), `terminee` (missions.closed_at > now()-24h), `en_echec` (last_error LIKE 'DEAD:%', processed_at IS NULL), limite 50 par colonne
- [X] T012 [P] [US2] Ajouter l'endpoint `POST /v1/triggers/{trigger_id}/retry` dans `api/routes/triggers.py` : 404 si non trouvé, 409 si `last_error` ne commence pas par `DEAD:`, 409 si `processed_at IS NOT NULL` ; sinon reset `last_error=None, claimed_at=None, claimed_by=None, attempts=0`, insert `SystemAudit(action="RETRY_TRIGGER")`, retourne `RetryResult` (T005)
- [X] T013 [P] [US2] Créer `web/components/KanbanTriggerCard.tsx` : affiche `source`, `tenant`, `received_at` (format relatif), `attempts`, `claimed_by` (si colonne réservée), snippet `last_error` ; bouton "Relancer" uniquement si `column === "en_echec"` avec `onRetry` callback + état de chargement pour éviter double-clic
- [X] T014 [US2] Créer `web/components/MissionsKanban.tsx` : composant client, `useQuery({ queryKey: ["kanban"], queryFn: getMissionsKanban, refetchInterval: 8_000 })`, 4 colonnes avec titres FR ("En attente" / "Réservée" / "Terminée" / "En échec"), chaque colonne utilise `<KanbanTriggerCard>` (en_attente, reservee, en_echec) ou un affichage mission simple (terminee), mutation TanStack Query pour `retryTrigger` avec invalidation de `["kanban"]` (dépend de T013)
- [X] T015 [US2] Modifier `web/app/missions/page.tsx` : lire `searchParams.view` (`"table"` | `"kanban"`), ajouter deux boutons toggle "Tableau" / "Kanban" en haut à droite de la page, rendre `<MissionsKanban />` si `view === "kanban"`, conserver la table HTML existante si `view === "table"` ou absent — libellés en français (dépend de T014)

**Checkpoint** : US2 complète et testable indépendamment.

---

## Phase 5 : Histoire Utilisateur 3 — Cycle de vie d'une mission (Priorité : P3)

**Objectif** : Section "Cycle de vie" sur la page détail mission + auto-refresh.

**Test indépendant** : Ouvrir `/missions/<id>` pour une mission avec attempts≥2, vérifier la frise chronologique (Reçu → Réservé → Mission créée → Traité).

### Implémentation US3

- [X] T016 [P] [US3] Ajouter l'endpoint `GET /v1/missions/{mission_id}/lifecycle` dans `api/routes/missions.py` : `_get_or_404(mission_id)`, puis `select(Trigger).where(Trigger.mission_id == mission_id).limit(1)`, retourne `MissionLifecycle` (T005) avec tous les champs trigger + mission ; si pas de trigger, champs trigger à `None`
- [X] T017 [P] [US3] Créer `web/components/MissionLifecycle.tsx` : composant client, props `{ missionId: string }`, `useQuery({ queryKey: ["lifecycle", missionId], queryFn: () => getMissionLifecycle(missionId), refetchInterval: (data) => data?.mission_status !== "CLOSED" ? 3_000 : false })`, frise chronologique 4 étapes : "Reçu" (received_at) → "Réservé" (claimed_at, affiche claimed_by) → "Mission créée" (mission_created_at) → "Traité" (mission_closed_at) — chaque étape avec horodatage formaté ou grisée si null, affiche `attempts` et snippet `last_error`
- [X] T018 [US3] Modifier `web/app/missions/[id]/page.tsx` : importer et insérer `<MissionLifecycle missionId={mission.mission_id} />` dans la page de détail après le titre de la mission et avant la section audit, convertir la page en client component `"use client"` avec `useQuery` pour l'auto-refresh de la mission (refetchInterval 3s si `status !== "CLOSED"`) (dépend de T017)

**Checkpoint** : US3 complète et testable indépendamment.

---

## Phase 6 : Histoire Utilisateur 4 — Surveillance temps réel (Priorité : P4)

**Objectif** : Page Surveillance avec graphiques Recharts + auto-refresh.

**Test indépendant** : Ouvrir `/monitoring`, vérifier 3 graphiques Recharts mis à jour automatiquement, journal d'activité conservé en bas, aucun appel `limit=1` dans l'onglet Réseau du navigateur.

### Implémentation US4

- [X] T019 [P] [US4] Créer le ring buffer et l'endpoint `GET /v1/metrics/snapshot` dans `api/routes/metrics.py` : `_history: deque[dict] = deque(maxlen=60)` (module-level), fonction `push_history_point(depth, inflight)`, endpoint qui appelle `queue_stats()` + requête SQL `percentile_cont` sur `missions` (dernière heure) + counts `mission_completed_24h` / `mission_dead_total`, retourne `MetricsSnapshot` avec `history=list(_history)` (T005)
- [X] T020 [US4] Étendre la tâche de fond `_refresh_metrics` dans `api/main.py` pour appeler `push_history_point(stats["depth"] or 0, stats["inflight"] or 0)` à chaque cycle `METRICS_REFRESH_INTERVAL` — importer `push_history_point` depuis `api/routes/metrics.py` (dépend de T019)
- [X] T021 [P] [US4] Créer `web/components/MonitoringCharts.tsx` : composant client `"use client"`, importer depuis `recharts` : `LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer`, `useQuery({ queryKey: ["metrics"], queryFn: getMetricsSnapshot, refetchInterval: 10_000 })`, 3 graphiques : (1) LineChart sur `data.history` (depth + inflight), (2) BarChart `[p50, p95, p99]` en secondes, (3) PieChart `completed_24h` vs `dead_total` — couleurs via CSS variables Marcel `var(--mrcl-persistent-content-default)`
- [X] T022 [US4] Réécrire `web/app/monitoring/page.tsx` : supprimer le polling antipattern (`setInterval` + `listMissions({limit:1})`), insérer `<MonitoringCharts />`, conserver le journal d'activité et la section "Diagnostics actifs" existante en bas de page, traduire tous les libellés en français (dépend de T021)

**Checkpoint** : US4 complète et testable indépendamment.

---

## Phase 7 : Histoire Utilisateur 5 — Catalogue Agents & Compétences (Priorité : P5)

**Objectif** : Pages `/admin/agents` et `/admin/skills` lisant les fichiers `agents/*/SKILL.md`.

**Test indépendant** : Ouvrir `/admin/agents`, vérifier 6 fiches agent. Ouvrir `/admin/skills`, filtrer par "infrastructure" → seuls k8s/GCP SRE apparaissent.

### Implémentation US5

- [X] T023 [P] [US5] Implémenter `GET /v1/admin/agents/catalog` dans `api/routes/admin.py` : `AGENTS_DIR = Path(__file__).parent.parent.parent / "agents"`, glob `*/SKILL.md`, parse frontmatter YAML (import yaml), retourne `list[AgentCard]` (T005) — `name` depuis frontmatter, `agent_dir` depuis `skill_file.parent.name`, `description` tronquée à 200 chars, `description_long` corps du SKILL.md tronqué à 500 chars, `active=True`
- [X] T024 [US5] Implémenter `GET /v1/admin/skills/catalog` dans `api/routes/admin.py` : même scan SKILL.md, extraire les skills depuis le corps markdown (lignes commençant par `-` et sections `##`), catégoriser par nom de dossier (`k8s_gcp_sre`/`prom_alerts_triage` → "infrastructure", `kafka_strimzi_expert` → "données", `intake`/`evidence_consolidator`/`post_mortem_analyst` → "autre"), retourne `list[SkillCard]` (T005) (dépend de T023 — même fichier)
- [X] T025 [P] [US5] Créer `web/app/admin/agents/page.tsx` : page client `"use client"`, `useQuery({ queryKey: ["agents"], queryFn: getAgentsCatalog })`, grille 3 colonnes de fiches agent (mrcl-card style via CSS Marcel tokens), chaque fiche : nom, description, version, `description_long`, badge "Actif" (`mrcl-tag variant="success"`) — libellés en français (dépend de T006 pour `getAgentsCatalog`)
- [X] T026 [P] [US5] Créer `web/app/admin/skills/page.tsx` : page client `"use client"`, `useQuery({ queryKey: ["skills"], queryFn: getSkillsCatalog })`, liste filtrable par catégorie via un select HTML ou `<select>` natif (catégories : "Toutes" / "infrastructure" / "données" / "externe" / "autre"), chaque entrée : agent associé, liste des skills, badge de catégorie — libellés en français (dépend de T006 pour `getSkillsCatalog`)
- [X] T027 [P] [US5] Créer les dossiers et fichiers nécessaires : `mkdir -p web/app/admin/agents web/app/admin/skills`, vérifier que les routes Next.js sont reconnues
- [X] T028 [US5] Modifier `web/components/SideBar.tsx` : ajouter un groupe "Administration" (s'il n'existe pas) avec les liens "Agents" (`/admin/agents`) et "Compétences" (`/admin/skills`) — libellés en français, icône Lucide appropriée (ex. `Bot`, `Layers`) (dépend de T025, T026)

**Checkpoint** : US5 complète et testable indépendamment.

---

## Phase 8 : Histoire Utilisateur 6 — Suivi des coûts LLM (Priorité : P6) ⚠️ Conditionnel

**Prérequis** : Validation que Langfuse self-hosted expose `/api/public/traces` avec `usage.totalTokens` et `usage.totalCost`. Implémenter uniquement si validé.

**Test indépendant** : Ouvrir `/cost`, vérifier tableau par tenant×env×agent et graphique tendance 7j. Si Langfuse indisponible, vérifier message d'indisponibilité en français.

### Implémentation US6

- [ ] T029 [US6] Créer `api/routes/cost.py` : endpoint `GET /v1/cost/aggregate` — proxy Langfuse REST (`LANGFUSE_HOST + /api/public/traces`), authentification Basic (`LANGFUSE_PUBLIC_KEY:LANGFUSE_SECRET_KEY`), agrégation par tenant/env/agent depuis `metadata`, calcul coût estimé si `usage.totalCost` absent (multiplicateur rate Gemini 2.5 Flash-Lite), retourne 503 + message JSON si Langfuse inaccessible ; enregistrer le router dans `api/main.py`
- [ ] T030 [P] [US6] Créer `web/app/cost/page.tsx` : page client, `useQuery({ queryKey: ["cost"], queryFn: getCostAggregate })`, tableau par tenant×env×agent (tokens entrée/sortie, coût estimé), Recharts AreaChart tendance 7j, gestion explicite du cas "données non disponibles" (message en français + lien Langfuse) (dépend de T006 pour `getCostAggregate` à ajouter dans `web/lib/api.ts`)
- [ ] T031 [US6] Modifier `web/components/SideBar.tsx` : ajouter lien "Coûts" (`/cost`) avec icône Lucide `DollarSign` dans le groupe "Administration" (dépend de T030)

**Checkpoint** : US6 complète et testable indépendamment.

---

## Phase 9 : Polish & Vérifications

**Objectif** : Non-régression, typage TypeScript, labels français universels.

- [X] T032 [P] Vérifier l'absence d'erreurs TypeScript : `cd web && npx tsc --noEmit` — corriger toutes les erreurs avant de terminer
- [X] T033 [P] Vérifier la non-régression des tests back-end : `uv run pytest tests/unit/ -q --tb=short` — 170 tests doivent passer
- [X] T034 Valider les 5 scénarios de `specs/013-hermes-ui-refonte/quickstart.md` manuellement : OpsStrip+AttentionCard, Kanban+Relancer, Lifecycle, Monitoring, Agents/Skills — cocher chaque critère de succès

---

## Dépendances & Ordre d'exécution

### Dépendances entre phases

- **Setup (Phase 1)** : Aucune dépendance — démarrer immédiatement
- **Fondations (Phase 2)** : Dépend de Phase 1 — **BLOQUE toutes les histoires utilisateur**
- **US1-US4 (Phases 3-6)** : Dépendent des Fondations — peuvent démarrer en parallèle après Phase 2
- **US5 (Phase 7)** : Dépend des Fondations — peut démarrer après Phase 2
- **US6 (Phase 8)** : Dépend de US5 pour SideBar — conditionnel à validation Langfuse
- **Polish (Phase 9)** : Dépend de toutes les phases US terminées

### Dépendances entre histoires utilisateur

- **US1 (P1)** : Aucune dépendance sur les autres US
- **US2 (P2)** : Aucune dépendance sur US1 (fondations suffisent)
- **US3 (P3)** : Aucune dépendance sur US1/US2 (fondations suffisent)
- **US4 (P4)** : Aucune dépendance sur US1/US2/US3
- **US5 (P5)** : Aucune dépendance sur US1-US4
- **US6 (P6)** : Dépend de US5 pour les liens SideBar

### Au sein de chaque histoire utilisateur

- Back-end (endpoint) et front-end (composant) peuvent démarrer en parallèle dès que les Fondations sont complètes
- Composant `KanbanTriggerCard` avant `MissionsKanban` (T013 → T014)
- `MissionsKanban` avant la page missions (T014 → T015)
- `MissionLifecycle` composant avant modification page détail (T017 → T018)
- `MonitoringCharts` composant avant réécriture page monitoring (T021 → T022)
- Ring buffer avant extension background task (T019 → T020)

---

## Exemples d'exécution parallèle

### Fondations (Phase 2)

```text
Parallèle :
  T003 — Étendre web/marcel.d.ts
  T004 — Ajouter colonnes ORM core/models.py
  T006 — Ajouter fonctions web/lib/api.ts
Séquentiel après T004 :
  T005 — Ajouter schémas Pydantic api/schemas.py
```

### US1 (Phase 3)

```text
T007 — Enrichir /healthz api/main.py (back)
Parallèle (après T007 démarre) :
  T008 — Créer OpsStrip.tsx (front)
  T009 — Créer AttentionCard.tsx (front)
Séquentiel :
  T010 — Modifier layout.tsx (dépend T008+T009)
```

### US2 (Phase 4)

```text
Parallèle :
  T011 — Endpoint /kanban api/routes/missions.py
  T012 — Endpoint /retry api/routes/triggers.py
  T013 — Créer KanbanTriggerCard.tsx
Séquentiel :
  T014 — Créer MissionsKanban.tsx (dépend T013)
  T015 — Modifier missions/page.tsx (dépend T014)
```

### US4 (Phase 6)

```text
Parallèle :
  T019 — Ring buffer + endpoint /metrics/snapshot
  T021 — Créer MonitoringCharts.tsx
Séquentiel après T019 :
  T020 — Étendre _refresh_metrics api/main.py
Séquentiel après T021 :
  T022 — Réécrire monitoring/page.tsx
```

---

## Stratégie d'implémentation

### MVP (Histoire Utilisateur 1 uniquement)

1. Terminer Phase 1 : Setup
2. Terminer Phase 2 : Fondations (CRITIQUE)
3. Terminer Phase 3 : US1 — OpsStrip + AttentionCard
4. **VALIDER** : OpsStrip visible sur toutes les pages, AttentionCard conditionnelle
5. Déployer/démo si prêt

### Livraison incrémentale recommandée

1. Setup + Fondations → Base prête
2. US1 → OpsStrip live (MVP opérationnel)
3. US2 → Kanban + Relancer (réduction temps de réaction)
4. US3 → Lifecycle (utilité post-mortem)
5. US4 → Monitoring graphique (détection dégradation lente)
6. US5 → Catalogue agents (onboarding)
7. US6 → Coûts LLM (conditionnel Langfuse)

### Stratégie équipe parallèle

Après Phase 2 terminée :
- Développeur A : US1 + US2 (shell + kanban)
- Développeur B : US3 + US4 (détail mission + monitoring)
- Développeur C : US5 (catalogue agents/skills)

---

## Notes

- `[P]` = fichiers différents, aucune dépendance sur une tâche incomplète
- `[Story]` = traçabilité vers les histoires utilisateur de `spec.md`
- Chaque histoire est indépendamment testable et livrable
- US6 est conditionnelle — ne pas bloquer les autres US en attendant la validation Langfuse
- Les constantes back-end (statuts BD, codes erreur, noms de fichiers) restent en anglais — seule l'UI est en français
- Ne pas toucher `agents/pipeline/orchestrator.py:158-193` (GKE token-patch)
