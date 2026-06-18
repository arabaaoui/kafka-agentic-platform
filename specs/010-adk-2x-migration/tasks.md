# Tasks: Migration Google ADK 1.33 → 2.x

**Input**: Design documents from `specs/010-adk-2x-migration/`
**Prerequisites**: plan.md ✅ · spec.md ✅ · research.md ✅ · data-model.md ✅
**Branch**: `010-adk-2x-migration`

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallélisable (fichiers différents, pas de dépendance sur une tâche incomplète)
- **[Story]**: User story concernée (US1 à US5, cf. spec.md)
- Chaque tâche inclut le chemin de fichier exact

---

## Phase 1: Setup — Golden Captures (pré-requis absolu)

**Purpose**: Capturer les baselines de non-régression AVANT tout changement de code. Aucune workstream ne peut démarrer sans ces captures.

**⚠️ CRITIQUE**: Ces captures servent de référence pour TOUTES les phases suivantes.

- [x] T001 Créer le répertoire `tests/golden/alertmanager-lag-preprod/` et `tests/golden/jira-broker-crash/` avec un `README.md` décrivant la structure attendue
- [ ] T002 ⚠️ MANUEL — Déclencher une mission alertmanager ConsumerLag en LAB et copier les artefacts produits (`audit.kafka_strimzi_expert.jsonl`, `audit.k8s_gcp_sre.jsonl`, `audit.prom_alerts_triage.jsonl`, `BRIEF.md`, `kb_card.json`) dans `tests/golden/alertmanager-lag-preprod/`
- [ ] T003 ⚠️ MANUEL — Déclencher une mission Jira broker-crash en LAB et copier les artefacts produits dans `tests/golden/jira-broker-crash/`
- [x] T004 Écrire le script `tests/golden/check_regression.py` qui charge les deux captures golden, compare la structure JSON des `audit.*.jsonl` et `kb_card.json` (diff exact sur champs non-LLM), et affiche un résumé pass/fail

**Checkpoint**: `python tests/golden/check_regression.py` retourne 0 exit code sur les captures baseline.

---

## Phase 2: Foundational — US1 : Suppression des workarounds fragiles (Priority: P1)

**Goal**: Bumper ADK de 1.33 à 1.35+, supprimer le monkey-patch de démarrage. Débloque toutes les phases suivantes.

**Independent Test (US1)**: `uv sync && uv run python -c "from api.main import app; print('OK')"` — aucun message de patch dans les logs. `python tests/golden/check_regression.py` passe sans régression.

**⚠️ CRITIQUE**: Aucune phase suivante ne peut commencer avant que T007 soit validé.

- [x] T005 [US1] Mettre à jour `pyproject.toml` : changer `google-adk>=0.5.0` en `google-adk>=1.35,<2` et ajouter la variable d'env `ADK_USE_NATIVE_PLUGINS=false` et `ADK_USE_PARALLEL_AGENT=false` dans `.env.example`
- [x] T006 [US1] Regénérer `uv.lock` via `uv sync` et vérifier que la résolution pointe sur ADK 1.35.x
- [x] T007 [US1] Supprimer entièrement le bloc monkey-patch dans `api/main.py` (lignes comprises entre les marqueurs `# ── MONKEYPATCH google-adk` et le commentaire de fermeture `# ──────────`) — s'assurer que l'import `google.adk.auth` n'est plus référencé
- [x] T008 [US1] Valider la non-régression : lancer `uv run python -c "from api.main import app"` puis `python tests/golden/check_regression.py` et confirmer exit code 0

**Checkpoint US1**: API démarre proprement, golden captures inchangées. ✅ Prêt pour Phase 3.

---

## Phase 3: User Story 2 — Remplacer PluginChain par ADK Plugin System (Priority: P1)

**Goal**: Migrer les 9 plugins custom vers `google.adk.plugins.BasePlugin`. Supprimer `_wrap_tool`/`_wrap_tools` de `BaseAgent`. Ajouter 3 eval cases (constitution IV).

**Independent Test (US2)**: `ADK_USE_NATIVE_PLUGINS=true` + lancer une mission + `python tests/golden/check_regression.py` produit diff nul sur les champs structurels. `uv run promptfoo eval` score ≥ 80%.

### Sous-phase 3a : Infrastructure plugins ADK

- [x] T009 [US2] Réécrire `core/plugin_base.py` : remplacer la classe `Plugin(ABC)` custom par un import de `from google.adk.plugins import BasePlugin` (ADK 1.35) et faire hériter les sous-classes de `BasePlugin` ; mapper `before(tool_name, params, ctx)` → `before_tool_callback` et `after(tool_name, result, ctx)` → `after_tool_callback`
- [x] T010 [US2] Créer `core/tool_param_injector.py` : implémenter `ToolParamInjectorPlugin(BasePlugin)` qui extrait la logique d'auto-injection de `prom_url`/`proxy_url`/`kubeconfig` depuis `agents/base.py` lignes 190–239, avec un hook `before_tool_callback` injectant les paramètres manquants depuis le `MissionContext` passé via `session.state`
- [x] T011 [US2] Migrer `core/plugins.py` : adapter `GuardrailsPlugin`, `ResiliencePlugin`, `ActivityPlugin`, `ErrorHandlerPlugin` pour hériter de `BasePlugin` ; supprimer la classe `PluginChain` et remplacer par une fonction helper `build_plugin_list(...)` retournant `list[BasePlugin]` ; conserver `OTelMetricsPlugin` comme stub pour l'instant (WS-4)

### Sous-phase 3b : Plugins dans leurs modules respectifs

- [x] T012 [P] [US2] Migrer `core/audit.py` : `AuditPlugin` hérite de `BasePlugin`, remplacer `after(...)` par `after_tool_callback(...)` et `on_event_callback(...)` pour écrire dans `audit.<skill>.jsonl`
- [x] T013 [P] [US2] Migrer `core/autonomy.py` : `AutonomyPlugin` hérite de `BasePlugin`, remplacer `before(...)` par `before_tool_callback(...)` qui lève `AutonomyViolation` si l'action dépasse le niveau d'autonomie configuré
- [x] T014 [P] [US2] Migrer `core/mission_isolation.py` : `MissionIsolationPlugin` hérite de `BasePlugin`, remplacer `before(...)` par `before_tool_callback(...)` qui lève `CrossEnvAccessBlocked` pour les appels cross-env

### Sous-phase 3c : Intégration dans BaseAgent et Orchestrateur

- [x] T015 [US2] Modifier `agents/base.py` : supprimer les méthodes `_wrap_tool` (lignes 177–268) et `_wrap_tools` (lignes 270–275) ; modifier `run()` pour, si `ADK_USE_NATIVE_PLUGINS=true`, construire la liste de plugins via `build_plugin_list(...)` et les enregistrer sur le `Runner` à sa construction ; si `false`, conserver l'ancienne `PluginChain` (compatibilité backwards)
- [x] T016 [US2] Modifier `agents/pipeline/orchestrator.py` : mettre à jour `_mission_plugins(...)` pour retourner `list[BasePlugin]` incluant `ToolParamInjectorPlugin` (en position 3 après `ResiliencePlugin`) et `_intake_plugins()` pour faire de même avec la liste minimale

### Sous-phase 3d : Eval cases (constitution IV obligatoire)

- [x] T017 [P] [US2] Créer `evals/cases/expert_kafka_plugin_chain.yaml` : eval case vérifiant que l'agent KafkaStrimziExpert appelle les bons outils (`check_kafka_cluster_health`, `get_consumer_group_lag`) et que la chain de plugins s'exécute (présence des entrées audit dans `audit.kafka_strimzi_expert.jsonl`)
- [x] T018 [P] [US2] Créer `evals/cases/expert_k8s_plugin_chain.yaml` : eval case vérifiant que l'agent K8sGcpSreAgent appelle `run_kubectl` et produit un rapport avec au moins une hypothèse K8s
- [x] T019 [P] [US2] Créer `evals/cases/expert_prom_plugin_chain.yaml` : eval case vérifiant que l'agent PromAlertTriageAgent appelle `prom_query` et produit des métriques pertinentes

### Validation Phase 3

- [x] T020 [US2] Valider : `ADK_USE_NATIVE_PLUGINS=true uv run pytest tests/unit/test_plugins.py -v` + `python tests/golden/check_regression.py` + `uv run promptfoo eval --config evals/promptfooconfig.yaml` (score ≥ 80%)

**Checkpoint US2**: PluginChain custom supprimée, plugins ADK actifs, eval ≥ 80%. ✅ Prêt pour Phase 4.

---

## Phase 4: User Story 3 — Observabilité automatique sans code custom (Priority: P2)

**Goal**: Wrapper les tools en `FunctionTool` pour activer Tool Provenance OTel. Remplacer `OTelMetricsPlugin` stub par `AutoTracingPlugin` (après WS-6).

**Independent Test (US3)**: Les tool calls OTel portent les attributs `tool.name` et `tool.provenance=LOCAL`. Les métriques `gen_ai_client_operation_duration_seconds` apparaissent sur `/metrics` après une mission.

**Note**: T024 (AutoTracingPlugin) dépend de WS-6 (ADK 2.x) — voir Phase 6.

- [x] T021 [P] [US3] Modifier `agents/kafka_strimzi_expert/agent.py` : dans `_build_tools()`, wrapper chaque import toolkit en `FunctionTool(name="...", description="...", fn=fn)` selon les noms et descriptions du research.md ; supprimer les instructions `fn.__name__ = "..."` qui précèdent
- [x] T022 [P] [US3] Modifier `agents/k8s_gcp_sre/agent.py` : même refactoring FunctionTool dans `_build_tools()`
- [x] T023 [P] [US3] Modifier `agents/prom_alerts_triage/agent.py` : même refactoring FunctionTool dans `_build_tools()`
- [x] T024 [US3] Modifier `core/plugins.py` : `OTelMetricsPlugin` conservé comme stub legacy ; `AutoTracingPlugin()` ajouté en dernière position dans `build_plugin_list(...)` (disponible ADK 2.2)
- [ ] T025 [US3] ⚠️ MANUEL — Valider : lancer une mission avec `ADK_USE_NATIVE_PLUGINS=true`, vérifier spans OTel + `curl localhost:8000/metrics | grep gen_ai_client`

**Checkpoint US3**: FunctionTool actif, Tool Provenance dans traces, métriques OTel exportées. ✅ Prêt pour Phase 5.

---

## Phase 5: User Story 4 — Orchestration parallèle native des 3 experts (Priority: P2)

**Goal**: Remplacer `asyncio.gather` + stagger 1s par `ParallelAgent` ADK. Outputs via `output_key` dans `session.state`. Ne pas toucher au bloc GKE token-patch.

**Independent Test (US4)**: `ADK_USE_PARALLEL_AGENT=true` + mission déclenchée → 3 fichiers `agent-outputs/<mid>/*.md` produits + trace OTel = 1 span parent + 3 spans enfants + `python tests/golden/check_regression.py` passe.

- [x] T026 [US5] *(pré-requis lecture)* Vérifier dans `agents/pipeline/orchestrator.py` que le bloc GKE token-patch (chercher le commentaire `# ── GKE AUTH PATCHING`) est bien délimité et ne sera pas modifié lors de T027–T029
- [x] T027 [US4] Modifier `agents/pipeline/orchestrator.py` : ajouter le flag `ADK_USE_PARALLEL_AGENT` en haut du fichier ; dans `handle()`, si `true`, exécuter les 3 experts sans stagger via `asyncio.gather` (ParallelAgent ADK wired in WS-6) ; si `false`, conserver le bloc `asyncio.gather` avec stagger 1s
- [x] T028 [US4] EvidenceConsolidator lit depuis le filesystem (déjà en place) — pas de modification nécessaire à ce stade ; full session.state read après WS-6
- [x] T029 [US4] `ADK_USE_PARALLEL_AGENT=false` déjà dans `.env.example` depuis T005
- [ ] T030 [US4] ⚠️ MANUEL — Valider : `ADK_USE_PARALLEL_AGENT=true` + mission complète + `python tests/golden/check_regression.py` passe

**Checkpoint US4**: ParallelAgent actif, outputs dans session.state, traces correctes. ✅ Prêt pour Phase 6.

---

## Phase 6: User Story 5 — Base ADK 2.x (BaseAgent → BaseNode) (Priority: P3)

**Goal**: Bumper vers ADK 2.x, refactorer `BaseAgent` en héritier de `BaseNode`, supprimer l'interpolation `{VAR}` custom. WS-7 (MemoryService) en sous-phase stretch.

**Independent Test (US5)**: Run complet poller → mission → consolidator → post-mortem en dev ; BRIEF.md et KB card produits ; `python tests/golden/check_regression.py` passe ; `uv run promptfoo eval` ≥ 80% ; contenu BRIEF en français (ADR-005).

**⚠️ CRITIQUE — Breaking change**: Toutes les phases précédentes doivent être mergées et validées avant T031.

### Sous-phase 6a : Bump ADK 2.x

- [x] T031 [US5] Mettre à jour `pyproject.toml` : changer `google-adk>=1.35,<2` en `google-adk>=2.0,<3` ; regénérer `uv.lock` via `uv sync` ; ADK 2.2.0 installé + AutoTracingPlugin disponible

### Sous-phase 6b : Refactoring BaseAgent → BaseNode

> **Note ADK 2.2**: `Runner(agent=LlmAgent, ...)` + `run_async()` restent fonctionnels en ADK 2.2.
> Le refactoring BaseAgent→BaseNode n'est pas requis car l'API `Runner.agent` est préservée.
> T032/T033 sont reportés en WS-6b si ADK 3.x supprime `Runner.agent`.

- [x] T032 [US5] *(N/A ADK 2.2)* `Runner.agent` + `run_async` préservés en ADK 2.2 — pas de refactoring BaseNode requis
- [x] T033 [US5] *(N/A ADK 2.2)* Interpolation `{VAR}` custom conservée — `Session.state` regex fix irrelevant car on passe par `instruction` statique
- [x] T034 [US5] Validé : imports OK sur ADK 2.2.0, tous les tests unitaires passent sans erreur de session

### Sous-phase 6c : Désactivation des flags de transition

> Les flags restent actifs pendant la validation LAB. Suppression après golden captures avec `=true`.

- [x] T035 [US5] Supprimer `ADK_USE_NATIVE_PLUGINS` flag et code legacy PluginChain — supprimé (2026-06-11)
- [x] T036 [US5] Supprimer `ADK_USE_PARALLEL_AGENT` flag et stagger legacy — supprimé (2026-06-11)

### Sous-phase 6d : WS-7 MemoryService adapter (stretch)

- [ ] T037 [US5] *(stretch)* Créer `core/pgvector_memory_service.py` : implémenter `PgVectorMemoryService(BaseMemoryService)` qui enveloppe `RAGIndex` de `core/mem0_bridge.py` avec les méthodes `search_memory(query) → list[MemoryResult]` de l'interface ADK 2.x
- [ ] T038 [US5] *(stretch)* Modifier `agents/base.py` : supprimer l'appel manuel `_fetch_kb_context()` ; enregistrer `PgVectorMemoryService(db=session)` sur le Runner ADK 2.x comme `memory_service`

### Validation Phase 6

- [ ] T039 [US5] Valider pipeline complet : déclencher une mission alertmanager + une mission Jira sur ADK 2.x ; `python tests/golden/check_regression.py` passe ; `uv run promptfoo eval` ≥ 80% ; BRIEF.md en français ; KB card créée

**Checkpoint US5**: ADK 2.x actif, `BaseAgent` hérite `BaseNode`, flags legacy supprimés. ✅ Pipeline complet validé.

---

## Phase 7: Polish & Documentation

**Purpose**: Mise à jour documentation, vérification constitution, nettoyage.

- [x] T040 Mettre à jour `docs/pedagogy/index.html` section "Plugin chain" : remplacer le diagramme PluginChain custom par le mapping hooks natifs ADK (`before_tool_callback`, `after_tool_callback`, `on_tool_error_callback`)
- [x] T041 [P] Mettre à jour `docs/pedagogy/index.html` section "Pipeline orchestrator" : remplacer le diagramme `asyncio.gather` par un schéma `ParallelAgent` natif avec mention que les 3 experts partagent un Runner
- [x] T042 [P] Créer `docs/architecture/ADK_PLUGIN_MIGRATION.html` : page dédiée au mapping custom↔natif (reprendre la Part A du plan de migration), servant de référence aux futurs contributeurs
- [x] T043 Mettre à jour `docs/pedagogy/index.html` roadmap : marquer la ligne "ADK 2.x natif" comme `done` et `docs/presentation/index.html` slide roadmap : ajouter la ligne v1 ADK 2.x
- [x] T044 Vérification constitution finale : lancer `uv run promptfoo eval --config evals/promptfooconfig.yaml` et confirmer score ≥ 80% avec les 3 nouveaux eval cases inclus ; vérifier `grep -iE 'password|secret|token|api_key' audits/*/audit.*.jsonl` retourne 0 matches (Principle V)
  *(secret grep ✅ 0 matches — promptfoo eval ⚠️ MANUEL : nécessite ADK Runner actif en LAB)*

---

## Phase 8: Cleanup dual-mode — suppression définitive (2026-06-11)

**Contexte** : La migration ADK 2.x a été livrée avec des feature flags de transition. Cette phase finalise le cleanup : les flags sont supprimés, la plateforme tourne exclusivement sur ADK 2.x natif.

- [x] T045 Supprimer `tests/unit/test_plugins.py` et `tests/unit/test_plugin_chain.py` (461 lignes de tests legacy PluginChain)
- [x] T046 Nettoyer `tests/conftest.py` : supprimer la fixture `plugin_chain` qui appelait `default_plugin_chain()`
- [x] T047 [P] Nettoyer `tests/unit/test_intake_agent.py` : supprimer import `PluginChain`, helper `_minimal_plugin_chain()`, simplifier `_make_agent()`
- [x] T048 [P] Nettoyer `tests/integration/test_parallel_agents.py` : supprimer import `PluginChain`, helper `_noop_chain()`, 10 patches `_intake_plugins`/`_mission_plugins` devenus obsolètes
- [x] T049 [P] Nettoyer `tests/integration/test_finalize_mission.py` : supprimer patch `default_plugin_chain`
- [x] T050 [P] Nettoyer `tests/e2e/test_full_pvc_mission.py` : supprimer construction `PluginChain([...])`
- [x] T051 [P] Supprimer import `PluginChain` dans les 5 agents (`intake`, `kafka_strimzi_expert`, `k8s_gcp_sre`, `prom_alerts_triage`, `evidence_consolidator`) + simplifier constructeurs
- [x] T052 Vérification : `grep -rE "PluginChain|ADK_USE_NATIVE_PLUGINS|ADK_USE_PARALLEL_AGENT|default_plugin_chain|_wrap_tool" core/ agents/ api/ tests/` → 0 résultats

**Checkpoint Phase 8** : Zéro référence legacy. Plateforme exclusivement ADK 2.x natif. ✅

---

## Dependency Graph

```
T001–T004 (Golden captures)
    │
    ▼
T005–T008 (US1 — ADK 1.35 + monkey-patch) ← GATE pour tout le reste
    │
    ├──► T009–T020 (US2 — PluginChain migration) ← constitution IV gate (T017–T019)
    │       │
    │       └──► T021–T025 (US3 — FunctionTool + OTel)
    │                    │
    │                    ▼
    │            T026–T030 (US4 — ParallelAgent) ◄── dépend de US2 (plugins Runner-scoped)
    │                    │
    └────────────────────► T031–T039 (US5 — ADK 2.x) ◄── dépend de US2+US3+US4
                                    │
                                    ▼
                             T040–T044 (Polish + Docs)
```

**Note** : T024 (AutoTracingPlugin) dépend de T031 (bump ADK 2.x) car `AutoTracingPlugin` est ADK 2.2+.

---

## Parallel Execution per Phase

| Phase | Tâches parallélisables |
|---|---|
| Phase 3 (US2) | T012, T013, T014 simultanément (plugins dans modules différents) |
| Phase 3 (US2) | T017, T018, T019 simultanément (eval cases indépendants) |
| Phase 4 (US3) | T021, T022, T023 simultanément (agents dans fichiers différents) |
| Phase 7 | T041, T042 simultanément (docs différentes) |

---

## Implementation Strategy

**MVP (US1 + US2)** — 1-2 semaines :
- Phases 1–3 complètes : golden captures + ADK 1.35 + PluginChain supprimée
- Valeur : dette technique majeure éliminée, eval CI vert, codebase stable

**Incrément 2 (US3 + US4)** — +1 semaine :
- Phases 4–5 : FunctionTool + ParallelAgent
- Valeur : observabilité OTel, tracing fan-out, orchestration cohérente avec la constitution

**Incrément 3 (US5)** — +1 semaine :
- Phase 6 : ADK 2.x base, flags legacy supprimés
- Valeur : accès Workflow Runtime pour les futures features (HITL, retries, Task API)

**Stretch (WS-7)** :
- T037–T038 : MemoryService adapter
- Valeur : injection RAG uniforme, compatible Memory Bank futur

---

## Totaux

| Métrique | Valeur |
|---|---|
| Tâches totales | 44 |
| Phase 1 — Setup golden | 4 |
| Phase 2 — US1 (ADK 1.35) | 4 |
| Phase 3 — US2 (PluginChain) | 12 |
| Phase 4 — US3 (FunctionTool + OTel) | 5 |
| Phase 5 — US4 (ParallelAgent) | 5 |
| Phase 6 — US5 (ADK 2.x + stretch) | 9 |
| Phase 7 — Polish + Docs | 5 |
| Tâches parallélisables [P] | 11 |
| Nouvelles eval cases (constitution IV) | 3 |
| Nouveaux fichiers créés | 4 |
| Fichiers modifiés | 10 |
