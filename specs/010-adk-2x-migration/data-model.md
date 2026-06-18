# Data Model — Migration Google ADK 1.33 → 2.x

**Produit par**: `/speckit.plan` Phase 1
**Date**: 2026-05-21

---

## Périmètre

Cette migration est un **refactoring technique pur**. Elle ne crée pas de nouvelles entités en base de données et ne modifie pas les tables PostgreSQL existantes (`missions`, `audits`, `kb_chunks`, `audit_chunks`, `triggers`, `filter_rules`, `tenants`).

Les seuls "modèles" introduits sont des constructs de configuration et de test.

---

## WorkstreamGate (construct de configuration)

Variable d'environnement contrôlant l'activation d'une workstream pendant la transition.

| Champ | Type | Valeur défaut | Description |
|---|---|---|---|
| `ADK_USE_NATIVE_PLUGINS` | `bool` (env string `"true"\|"false"`) | `false` | Active la PluginChain ADK native (WS-2) |
| `ADK_USE_PARALLEL_AGENT` | `bool` (env string `"true"\|"false"`) | `false` | Active le ParallelAgent natif (WS-5) |

Ces variables sont temporaires — elles disparaissent une fois le code legacy supprimé après validation de chaque workstream.

---

## GoldenCapture (construct de test, filesystem)

Snapshot d'une mission complète servant de référence de non-régression.

**Emplacement** : `tests/golden/<mission-slug>/`

```text
tests/golden/
├── alertmanager-lag-preprod/
│   ├── prompts.json           # [{agent, prompt_text}, ...]
│   ├── tool_calls.json        # [{agent, tool_name, params, result}, ...]
│   ├── audit.kafka_strimzi_expert.jsonl
│   ├── audit.k8s_gcp_sre.jsonl
│   ├── audit.prom_alerts_triage.jsonl
│   ├── BRIEF.md
│   └── kb_card.json
└── jira-broker-crash/
    └── [même structure]
```

**Règles de diff** :
- `prompts.json`, `tool_calls.json`, `kb_card.json` : diff structurel exact (clés + types)
- `audit.*.jsonl` : diff exact sur les champs non-LLM (`timestamp`, `tool_name`, `mission_id`)
- `BRIEF.md` : diff sémantique manuel (le texte LLM peut varier à l'identique)

---

## PluginRegistry (construct runtime, pas de persistance)

Liste ordonnée des plugins enregistrés sur le `Runner` ADK. Pas de modèle DB — c'est une construction en mémoire à la création du Runner.

**Ordre canonique** (inchangé par rapport à la PluginChain actuelle) :
1. GuardrailsPlugin
2. ResiliencePlugin
3. ToolParamInjectorPlugin *(nouveau — extrait de `_wrap_tool`)*
4. AuditPlugin
5. ActivityPlugin
6. Mem0MemoryPlugin *(à confirmer présence dans chain — cf. research.md)*
7. MissionIsolationPlugin
8. AutonomyPlugin
9. ErrorHandlerPlugin
10. AutoTracingPlugin *(remplace OTelMetricsPlugin — post WS-6)*

---

## Pas de migration de schéma DB

Aucune migration Alembic requise pour cette feature. Les tables existantes (`audit_chunks`, `kb_chunks`, `missions`, etc.) ne sont pas modifiées.
