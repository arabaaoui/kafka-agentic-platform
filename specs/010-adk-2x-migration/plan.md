# Implementation Plan: Migration Google ADK 1.33 → 2.x

**Branch**: `010-adk-2x-migration` | **Date**: 2026-05-21 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/010-adk-2x-migration/spec.md`

---

## Summary

Remplacer les abstractions Python custom de la plateforme (PluginChain, wrapping d'outils, asyncio.gather, OTelMetricsPlugin stub, monkey-patch ADK) par les primitives natives de Google ADK 2.x (Plugin System, FunctionTool, ParallelAgent, AutoTracingPlugin, BaseNode), en deux temps : stabilisation sur ADK 1.35 (WS-1 à WS-5), puis saut ADK 2.x (WS-6). Contrainte stricte : non-régression totale validée par golden captures avant toute workstream.

---

## Technical Context

**Language/Version**: Python 3.11+ (uv workspace)
**Primary Dependencies**: `google-adk` (1.33 → 1.35 → 2.x), `google-adk[otel]` pour AutoTracingPlugin, SQLAlchemy async, FastAPI
**Storage**: PostgreSQL 17 — aucune migration de schéma requise
**Testing**: pytest + golden captures filesystem (`tests/golden/`) + eval cases promptfoo (`evals/cases/`)
**Target Platform**: GKE LAB (Linux container, non-prod)
**Project Type**: Refactoring technique — web service + agentic pipeline
**Performance Goals**: Temps de mission non dégradé > 5% vs baseline ADK 1.33
**Constraints**: Non-régression stricte sur golden captures ; branche `main` déployable à tout moment
**Scale/Scope**: 7 workstreams séquentielles, ~3-4 semaines solo

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principe | Status | Justification |
|---|---|---|
| I — Read-Only v0 | ✅ PASS | Migration ne touche pas aux outils — aucun outil mutant n'est ajouté. MissionIsolationPlugin et AutonomyPlugin sont préservés avec les mêmes règles. |
| II — MissionIsolationPlugin enforced | ✅ PASS | `MissionIsolationPlugin` est migré vers le hook ADK natif `before_tool_callback` avec la **même logique de blocage**. Aucun relâchement des règles d'isolation. |
| III — Post Jira/Care = opt-in | ✅ PASS | Hors périmètre de cette migration. |
| IV — Eval Suite CI Blocking ≥80% | ⚠️ GATE | Les 3 agents experts sont modifiés (WS-2 plugin chain, WS-3 FunctionTool). **Obligation** : ajouter ≥1 eval case par agent avant merge (`evals/cases/expert_kafka_plugin_chain.yaml`, `expert_k8s_plugin_chain.yaml`, `expert_prom_plugin_chain.yaml`). Voir WS-2 et WS-3 dans le plan d'implémentation. |
| V — Zero Secret Leakage | ✅ PASS | `AuditPlugin` est migré vers hook natif sans modifier la logique de redaction. Le grep automatique sur `audit.jsonl` reste actif. |
| VI — Skills = SKILL.md | ✅ PASS | Aucun fichier SKILL.md modifié. |
| VII — Agnostic by Design | ✅ PASS | Aucune valeur Enterprise-spécifique introduite dans `core/` ou `agents/`. |
| VIII — Incident Filters = Postgres | ✅ PASS | Hors périmètre. |

**Constitution Stack Constraints** : La constitution liste explicitement `ParallelAgent`, `SequentialAgent`, `LoopAgent` comme primitives cibles — cette migration est **alignée** avec les contraintes de stack.

---

## Project Structure

### Documentation (cette feature)

```text
specs/010-adk-2x-migration/
├── plan.md              ← ce fichier
├── spec.md              ← spécification feature
├── research.md          ← décisions techniques (Phase 0)
├── data-model.md        ← entités runtime et test (Phase 1)
├── checklists/
│   └── requirements.md  ← checklist qualité spec
└── tasks.md             ← généré par /speckit.tasks
```

### Source Code (fichiers impactés)

```text
# Fichiers modifiés

api/
└── main.py                          # WS-1 : suppression monkey-patch lignes 5-30

core/
├── plugin_base.py                   # WS-2 : Plugin ABC → google.adk.plugins.Plugin
├── plugins.py                       # WS-2 : PluginChain supprimée, plugins migrent vers ADK
│                                    # WS-4 : OTelMetricsPlugin → supprimé
├── audit.py                         # WS-2 : AuditPlugin migré vers after_tool_callback
├── autonomy.py                      # WS-2 : AutonomyPlugin migré vers before_tool_callback
└── mission_isolation.py             # WS-2 : MissionIsolationPlugin migré

agents/
├── base.py                          # WS-2 : _wrap_tool/_wrap_tools supprimés (~90 lignes)
│                                    # WS-6 : BaseAgent → BaseNode, run() réécrit en event-yield
│                                    # WS-6 : interpolation {VAR} custom supprimée
├── pipeline/
│   └── orchestrator.py              # WS-5 : asyncio.gather → ParallelAgent
│                                    # WS-5 : output_key par expert, lecture via session.state
├── kafka_strimzi_expert/
│   └── agent.py                     # WS-3 : FunctionTool wrapper, drop fn.__name__ pattern
├── k8s_gcp_sre/
│   └── agent.py                     # WS-3 : FunctionTool wrapper
└── prom_alerts_triage/
    └── agent.py                     # WS-3 : FunctionTool wrapper

# Fichiers créés (nouveaux)

core/
└── tool_param_injector.py           # WS-2 : ToolParamInjectorPlugin (extrait de _wrap_tool)

tests/
└── golden/                          # Avant WS-1 : captures golden
    ├── alertmanager-lag-preprod/
    ├── jira-broker-crash/
    └── check_regression.py          # Script de diff golden

evals/cases/
├── expert_kafka_plugin_chain.yaml   # WS-2/WS-3 : constitution IV
├── expert_k8s_plugin_chain.yaml     # WS-2/WS-3 : constitution IV
└── expert_prom_plugin_chain.yaml    # WS-2/WS-3 : constitution IV

.env (update)
└── ADK_USE_NATIVE_PLUGINS=false     # WS-2 : feature flag
    ADK_USE_PARALLEL_AGENT=false     # WS-5 : feature flag
```

**Structure Decision**: Le projet utilise une architecture plate `core/` + `agents/` — pas de réorganisation de packages. Les fichiers modifiés sont chirurgicaux, aucun nouveau package créé sauf `core/tool_param_injector.py`.

---

## Implementation Approach par Workstream

### WS-0 — Golden Captures (pré-requis, avant tout code)

**Objectif** : Capturer les baselines de non-régression.

**Actions** :
1. Créer `tests/golden/` avec deux sous-dossiers de missions
2. Déclencher une mission alertmanager via `make dev` + payload synthétique ConsumerLag
3. Déclencher une mission Jira via le poller avec ticket broker crash
4. Pour chaque mission, copier : `prompts.json` (inspecté depuis les logs), `tool_calls.json`, les 3 `audit.*.jsonl`, le `BRIEF.md`, le `kb_card.json`
5. Écrire `tests/golden/check_regression.py` : charge les deux golden, compare la structure JSON et signale les diffs

**Validation** : Les 2 captures existent et le script `check_regression.py` tourne sans erreur.

---

### WS-1 — Bump ADK 1.35.x + suppression monkey-patch

**Fichiers** :
- `pyproject.toml` : `google-adk>=1.35,<2`
- `uv.lock` : regénéré via `uv sync`
- `api/main.py` : supprimer entièrement le bloc lignes 5-30 (entre les marqueurs `# ── MONKEYPATCH` et `# ───────────`)

**Validation** :
```bash
uv sync
uv run python -c "from api.main import app; print('OK')"
# Lancer une mission, comparer avec golden WS-0
uv run python tests/golden/check_regression.py
```

---

### WS-2 — Migrer PluginChain → ADK Runner Plugin System

**Fichiers** :
- `core/plugin_base.py` : remplacer le `Plugin` ABC local par import `from google.adk.plugins import BasePlugin` (ou équivalent ADK 1.35). Conserver les méthodes `before` / `after` en les mappant sur `before_tool_callback` / `after_tool_callback`.
- `core/plugins.py` : supprimer `PluginChain`. Migrer `GuardrailsPlugin`, `ResiliencePlugin`, `ActivityPlugin`, `ErrorHandlerPlugin`, `OTelMetricsPlugin` (garder stub le temps de WS-4).
- `core/audit.py` : `AuditPlugin` migré vers `after_tool_callback` + `on_event_callback`.
- `core/autonomy.py` : `AutonomyPlugin` migré vers `before_tool_callback`.
- `core/mission_isolation.py` : `MissionIsolationPlugin` migré vers `before_tool_callback`.
- `core/tool_param_injector.py` : **nouveau fichier** — `ToolParamInjectorPlugin` extrait de `BaseAgent._wrap_tool:190-239`. Hérite de `google.adk.plugins.BasePlugin`, hook `before_tool_callback`, injecte `prom_url`/`proxy_url`/`kubeconfig` si absent.
- `agents/base.py` : supprimer `_wrap_tool` et `_wrap_tools` (~90 lignes). Modifier `run()` pour enregistrer la liste de plugins sur le `Runner` au lieu de wrapper les tools. Conditionner avec `ADK_USE_NATIVE_PLUGINS`.
- `agents/pipeline/orchestrator.py` : `_mission_plugins()` retourne une liste de plugins ADK au lieu d'une `PluginChain`.
- `evals/cases/expert_kafka_plugin_chain.yaml` + `expert_k8s_*.yaml` + `expert_prom_*.yaml` : **nouveaux eval cases** (constitution IV).

**Feature flag** : `ADK_USE_NATIVE_PLUGINS=false` → PluginChain legacy. `=true` → Plugin ADK.

**Validation** :
```bash
ADK_USE_NATIVE_PLUGINS=true uv run pytest tests/unit/test_plugins.py
uv run python tests/golden/check_regression.py
uv run promptfoo eval --config evals/promptfooconfig.yaml
```

---

### WS-3 — FunctionTool wrapper dans les agents experts

**Fichiers** :
- `agents/kafka_strimzi_expert/agent.py` : dans `_build_tools()`, wrapper chaque import toolkit `fn` en `FunctionTool(name="...", description="...", fn=fn)`. Supprimer `fn.__name__ = "..."`.
- `agents/k8s_gcp_sre/agent.py` : idem.
- `agents/prom_alerts_triage/agent.py` : idem.

**Validation** :
```bash
# Vérifier que les tool calls OTel ont des noms corrects
ADK_USE_NATIVE_PLUGINS=true uv run python -c "
from agents.kafka_strimzi_expert.agent import KafkaStrimziExpertAgent
tools = KafkaStrimziExpertAgent(...)._build_tools()
assert all(hasattr(t, 'name') for t in tools), 'FunctionTool missing'
"
uv run python tests/golden/check_regression.py
```

---

### WS-4 — Remplacer OTelMetricsPlugin par AutoTracingPlugin

**Note** : `AutoTracingPlugin` est disponible depuis ADK 2.2. Cette workstream doit être exécutée **après WS-6** (saut 2.x), sauf si ADK 1.35 expose une version compatible (à vérifier lors de l'implémentation).

**Fichiers** :
- `core/plugins.py` : supprimer `OTelMetricsPlugin`.
- `agents/base.py` (ou `orchestrator.py`) : ajouter `AutoTracingPlugin()` à la liste des plugins Runner.

**Validation** :
```bash
curl -s http://localhost:8000/metrics | grep gen_ai_client_operation_duration
```

---

### WS-5 — ParallelAgent pour le fan-out des 3 experts

**Fichiers** :
- `agents/pipeline/orchestrator.py` :
  - Supprimer le bloc `asyncio.gather(*(run_expert(agent, i * 1.0) for i, agent in enumerate(experts)))` (lignes 256).
  - Créer un `ParallelAgent(sub_agents=[kafka, sre, triage])`.
  - Chaque expert configuré avec `output_key="kafka_output"` / `"sre_output"` / `"prom_output"`.
  - EvidenceConsolidator lit depuis `session.state["kafka_output"]` etc.
  - **NE PAS TOUCHER** bloc GKE token-patch (lignes 158-193).
  - `AsyncSession` BD par agent : passer via closure ou param, **pas** via `session.state`.

**Feature flag** : `ADK_USE_PARALLEL_AGENT=false` → asyncio.gather legacy. `=true` → ParallelAgent.

**Validation** :
```bash
ADK_USE_PARALLEL_AGENT=true uv run python tests/golden/check_regression.py
# Vérifier 3 spans enfants dans les traces OTel
```

---

### WS-6 — Saut ADK 2.x (BaseAgent → BaseNode)

**Pré-requis** : WS-1 à WS-5 validées et mergées.

**Fichiers** :
- `pyproject.toml` : `google-adk>=2.0,<3`.
- `uv.lock` : regénéré.
- `agents/base.py` :
  - `BaseAgent` hérite de `google.adk.agents.BaseAgent` (= `BaseNode` en 2.0).
  - Supprimer le loop manuel `runner.run_async` — remplacer par `_run_async_impl(ctx)` yieldant des `Event`.
  - Supprimer le bloc d'interpolation `{VAR}` custom (lignes 326-358) — utiliser `Session.state` natif.
  - Valider que la politique FR (ADR-005) est toujours appliquée via `instruction` du `LlmAgent`.

**Validation** :
```bash
uv sync
uv run python tests/golden/check_regression.py
uv run promptfoo eval --config evals/promptfooconfig.yaml
# Diff BRIEF.md produit vs golden baseline (sémantique)
```

---

### WS-7 — MemoryService adapter pour RAG pgvector (stretch)

**Pré-requis** : WS-6.

**Fichiers** :
- `core/mem0_bridge.py` : `RAGIndex` enveloppé en classe `PgVectorMemoryService(BaseMemoryService)`. Méthodes : `search_memory(query) → list[MemoryResult]`.
- `agents/base.py` : supprimer `_fetch_kb_context()` manuel ; enregistrer `PgVectorMemoryService` sur le Runner.

**Validation** :
```bash
# Désactiver _fetch_kb_context, vérifier que RAG injecte quand même via MemoryService
uv run python tests/golden/check_regression.py
```

---

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Principle IV gate (eval cases) | 3 agents modifiés structurellement (WS-2, WS-3) | Les eval cases existants ne couvrent pas le comportement post-migration des plugins — un faux positif d'eval masquerait une régression. |

---

## Séquence de merge recommandée

```
WS-0 (golden) → WS-1 → WS-2 → WS-3 → WS-5 → WS-4+WS-6 (simultané) → WS-7 (stretch)
```

Chaque WS = 1 commit réversible. Merge sur `main` après `check_regression.py` vert + eval ≥80%.
