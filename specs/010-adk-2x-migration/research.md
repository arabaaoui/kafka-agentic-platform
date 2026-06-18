# Research — Migration Google ADK 1.33 → 2.x

**Produit par**: `/speckit.plan` Phase 0
**Date**: 2026-05-21
**Feature**: 010-adk-2x-migration

---

## Décision 1 — Stratégie de version : migration en deux temps

**Decision**: Bump ADK 1.35.x en premier (WS-1 à WS-5), saut 2.x ensuite (WS-6).

**Rationale**: ADK 2.0 (mai 2026) introduit une rupture breaking : `BaseAgent` hérite de `BaseNode`, `_run_async_impl()` est interdit, les events doivent être yieldés. En stabilisant d'abord sur 1.35 avec les workstreams à faible risque (suppression monkey-patch, plugins natifs, FunctionTool, AutoTracingPlugin, ParallelAgent), le saut 2.x devient un diff minimal. Chaque workstream peut être validée indépendamment avant la suivante.

**Alternatives considérées**:
- *Saut direct 1.33 → 2.0* : rejeté — trop de surface de changement simultanée, impossible de bisect un bug.
- *Rester en 1.35 indéfiniment* : rejeté — la constitution cible explicitement `ParallelAgent`/`SequentialAgent`/`LoopAgent` (Stack Constraints). ADK 2.x est le futur standard du projet.

---

## Décision 2 — ADK Plugin System : API native vs custom Plugin ABC

**Decision**: Migrer chaque plugin custom (héritant de `core/plugin_base.py:Plugin`) vers `google.adk.plugins.Plugin` (disponible depuis ADK 1.7). Enregistrer la liste ordonnée sur le `Runner` à sa construction.

**Rationale**: Les hooks natifs ADK (`before_tool_callback`, `after_tool_callback`, `on_tool_error_callback`, `before_model_callback`, `after_model_callback`) couvrent exactement les points d'extension utilisés par la `PluginChain` custom. L'enregistrement sur le `Runner` garantit un ordre d'exécution déterministe et visible.

**Mapping custom → natif**:

| Plugin custom | Hook(s) ADK natif | Notes |
|---|---|---|
| GuardrailsPlugin | `before_tool_callback` | Bloque les outils interdits avant exécution |
| ResiliencePlugin | `before_tool_callback` + `on_tool_error_callback` | Retry / circuit-breaker |
| OTelMetricsPlugin | **supprimé** → AutoTracingPlugin | Remplacé par plugin officiel ADK (décision 4) |
| AuditPlugin | `after_tool_callback` + `on_event_callback` | Écrit `audit.<skill>.jsonl` |
| ActivityPlugin | `after_tool_callback` | Log d'activité mission |
| Mem0MemoryPlugin | `after_tool_callback` (premier appel) | Injecte contexte RAG — à vérifier présence dans chain |
| MissionIsolationPlugin | `before_tool_callback` | Bloque les appels cross-env |
| AutonomyPlugin | `before_tool_callback` | Filtre selon niveau L2/L3/L4 |
| ErrorHandlerPlugin | `on_tool_error_callback` | Capture erreurs, formatte pour l'audit |

**Nouveau plugin à créer**: `ToolParamInjectorPlugin` — reprend la logique d'auto-injection de `prom_url`/`proxy_url`/`kubeconfig` actuellement dans `BaseAgent._wrap_tool` (lignes 190-239). S'intercale en `before_tool_callback` après `MissionIsolationPlugin`.

**Alternatives considérées**:
- *Garder la PluginChain custom en parallèle* : rejeté — double chemin de code, maintenance inutile.
- *Migrer plugins un par un sans feature flag* : rejeté — trop risqué si un plugin individuel casse la chaine.

---

## Décision 3 — ParallelAgent : session state vs filesystem pour les outputs agents

**Decision**: Utiliser `output_key` sur chaque sous-agent expert pour écrire dans `session.state`. L'EvidenceConsolidator lit depuis `session.state["kafka_output"]` etc. plutôt que depuis le disque.

**Rationale**: Avec un seul `Runner` pilotant le `ParallelAgent`, les sous-agents partagent la même session. `output_key` est le mécanisme natif pour passer les résultats entre nœuds. Cela supprime le pattern `_read_expert_outputs()` depuis disque dans le consolidator.

**Attention sur `AsyncSession` SQLAlchemy**: Les sessions BD (`agent_session`) ne sont pas sérialisables dans `session.state`. Elles doivent continuer à être fournies via un callable ou un contexte externe, pas via l'état de session ADK.

**Bloc GKE token-patch** (`orchestrator.py:158-193`): Reste inchangé, s'exécute AVANT l'instanciation du `ParallelAgent`. Ce bloc résout un problème d'authentification K8s orthogonal à ADK — aucune modification.

**Alternatives considérées**:
- *Conserver les fichiers disque comme canal de communication* : rejeté — couplage fort sur le filesystem, incompatible avec les Workflow Runtime futures.
- *Utiliser Redis comme bus* : rejeté — sur-ingénierie, pas de consommateur Redis pour ce pattern.

---

## Décision 4 — AutoTracingPlugin vs OTelMetricsPlugin custom

**Decision**: Supprimer `OTelMetricsPlugin` (stub no-op) et enregistrer `AutoTracingPlugin()` d'ADK 2.2 sur le Runner. Les métriques Prometheus `Counter`/`Summary` dans `core/mem0_bridge.py` sont conservées (orthogonales à OTel).

**Rationale**: `AutoTracingPlugin` est une ligne de configuration qui exporte automatiquement les spans `gen_ai.client.*` (outil, modèle, tokens) vers tout backend OTel configuré. Cela élimine ~7 lignes de stub vide et fournit immédiatement des traces exploitables dans Langfuse ou Grafana Tempo.

**Prérequis**: `AutoTracingPlugin` est disponible depuis ADK 2.2. Cette workstream dépend donc du saut 2.x (WS-6) **ou** doit être faite après le bump vers une version 2.x beta si disponible en 1.35. À valider lors de WS-4 si 1.35 l'exporte.

**Alternatives considérées**:
- *Instrumenter manuellement chaque outil avec span OTel* : rejeté — code de traçage couplé au code métier.
- *Garder le stub* : rejeté — metriques vides = pas de visibilité opérationnelle.

---

## Décision 5 — FunctionTool : wrapping explicite vs introspection

**Decision**: Wrapper chaque outil toolkit avec `FunctionTool(name=..., description=..., fn=fn)` dans `_build_tools()`. Supprimer le pattern `fn.__name__ = "..."`.

**Rationale**: `FunctionTool` expose `name` et `description` comme attributs de premier ordre, ce qui permet à ADK d'émettre des `Tool Provenance` events (`LOCAL`) et d'alimenter les métriques OTel avec des labels outil corrects. La mutation de `__name__` est un hack fragile.

**Impact**: 3 fichiers concernés — `agents/kafka_strimzi_expert/agent.py`, `agents/k8s_gcp_sre/agent.py`, `agents/prom_alerts_triage/agent.py`. Changement isolé, aucune logique métier modifiée.

---

## Décision 6 — BaseAgent → BaseNode (ADK 2.0) : pattern event-yielding

**Decision**: `BaseAgent` hérite de `google.adk.agents.BaseAgent` (qui est `BaseNode` en 2.0). Remplacer le loop manuel `runner.run_async` → `async for event in runner.run_async(...)` par la méthode `_run_async_impl(ctx)` yieldant des `Event` objects.

**Rationale**: ADK 2.0 interdit le pattern "run loop externe" — les sous-classes de `BaseNode` doivent yield leurs events depuis `_run_async_impl`. La session state dans ADK 2.x supporte correctement les accolades littérales (regex corrigée) → le bloc d'interpolation `{VAR}` manuel (`base.py:326-358`) peut être supprimé.

**Compatibilité sessions**: ADK 2.x lit les sessions créées par ADK 1.28+. Les missions en cours au moment du déploiement WS-6 doivent être terminées ou explicitement invalidées (purge de `InMemorySessionService` qui redémarre de toute façon à chaque process restart).

**Alternatives considérées**:
- *Sous-classer LlmAgent directement* : rejeté — `LlmAgent` n'est pas conçu pour être sous-classé en 2.x, contrairement à `BaseNode`.
- *Wrapper ADK dans un adaptateur sans héritage* : rejeté — perd tous les bénéfices du Workflow Runtime.

---

## Décision 7 — Feature flags : variables d'environnement de bascule

**Decision**: Deux flags booléens d'environnement :
- `ADK_USE_NATIVE_PLUGINS` (défaut `false`) → active la PluginChain ADK native (WS-2)
- `ADK_USE_PARALLEL_AGENT` (défaut `false`) → active le ParallelAgent natif (WS-5)

Chaque flag passe à `true` après validation des golden captures. Le code legacy est supprimé au merge de la WS suivante.

**Rationale**: Permet de déployer progressivement sur l'environnement LAB et de comparer avant/après sur des missions réelles sans risque de régression non détectée.

---

## Décision 8 — Golden Captures : format et emplacement

**Decision**: Stocker dans `tests/golden/` (nouveau dossier). Deux missions capturées :
1. `alertmanager-lag-preprod/` — mission déclenchée par alerte ConsumerLag
2. `jira-broker-crash/` — mission déclenchée par ticket Jira broker crash

Pour chaque mission, capturer :
- `prompts.json` — liste des prompts envoyés au LLM par agent
- `tool_calls.json` — liste ordonnée des appels d'outils (nom, params, résultat)
- `audit.kafka_strimzi_expert.jsonl`, `audit.k8s_gcp_sre.jsonl`, `audit.prom_alerts_triage.jsonl`
- `BRIEF.md` — rapport final
- `kb_card.json` — KB card créée

**Script de diff**: `tests/golden/check_regression.py` — compare la structure JSON (exact) et signale les diffs de texte LLM (sémantique, pas byte-exact).

---

## Décision 9 — Constitution Principle IV : eval cases pour agents modifiés

**Decision**: Ajouter 1 eval case par agent expert modifié dans `evals/cases/`. Cibler le comportement visible : "l'agent Kafka identifie le bon root cause avec les bons outils appelés".

**Rationale**: Constitution Principle IV — tout agent modifié requiert ≥1 eval case avant merge. Les 3 agents experts (Kafka, K8s SRE, Prom) sont modifiés dans WS-2 (wrapping plugins) et WS-3 (FunctionTool). Il faut ajouter :
- `expert_kafka_plugin_chain.yaml`
- `expert_k8s_plugin_chain.yaml`
- `expert_prom_plugin_chain.yaml`

---

## Résumé des décisions

| # | Décision | Workstream | Risque |
|---|---|---|---|
| 1 | Migration deux temps (1.35 puis 2.x) | WS-1 → WS-6 | Faible |
| 2 | Plugins custom → ADK Plugin API | WS-2 | Moyen |
| 3 | ParallelAgent + output_key | WS-5 | Moyen |
| 4 | AutoTracingPlugin | WS-4 (post WS-6) | Faible |
| 5 | FunctionTool wrapper | WS-3 | Faible |
| 6 | BaseAgent → BaseNode | WS-6 | Élevé |
| 7 | Feature flags env | WS-2, WS-5 | Faible |
| 8 | Golden captures | Avant WS-1 | Faible |
| 9 | Eval cases constitution | WS-2 + WS-3 | Faible |
