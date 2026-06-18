# Feature Specification: Migration Google ADK 1.33 → 2.x

**Feature Branch**: `010-adk-2x-migration`
**Created**: 2026-05-21
**Status**: Draft
**Input**: Migration des abstractions custom Python vers les primitives natives Google ADK 2.x, sans régression fonctionnelle.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Mainteneur : supprimer les contournements fragiles (Priority: P1)

En tant que mainteneur de la plateforme, je veux que les contournements liés à une version figée d'ADK soient supprimés, afin que l'application démarre sans patch dynamique et que les futures mises à jour ADK ne nécessitent plus de workarounds manuels.

**Why this priority** : Le patch dynamique au démarrage de l'API et le contournement de la substitution de variables créent une fragilité directe — n'importe quelle mise à jour mineure d'ADK peut casser l'application sans avertissement. C'est le risque le plus immédiat.

**Independent Test** : Démarrer la plateforme depuis un environnement propre avec ADK 1.35+ — aucun message de patch au démarrage, aucune exception au chargement. La plateforme est pleinement opérationnelle en une seule commande de lancement.

**Acceptance Scenarios** :

1. **Given** la plateforme utilise ADK 1.35+, **When** le module principal est importé au démarrage, **Then** aucune modification dynamique du runtime ADK n'est effectuée.
2. **Given** une mission est déclenchée, **When** le contexte de session est peuplé avec des variables d'environnement, **Then** la substitution fonctionne sans code de contournement personnalisé.
3. **Given** une nouvelle version mineure d'ADK est publiée dans la plage supportée, **When** la dépendance est mise à jour, **Then** la plateforme démarre sans modifications de code supplémentaires.

---

### User Story 2 — Mainteneur : remplacer la chaîne de plugins custom par les hooks natifs ADK (Priority: P1)

En tant que mainteneur, je veux que les 9 comportements transversaux (sécurité, résilience, audit, mémoire, isolation, autonomie…) soient enregistrés via le système de plugins natif d'ADK, afin que le code de wrapping manuel des outils soit supprimé et que les comportements transversaux soient maintenables sans introspection de signatures Python.

**Why this priority** : Le wrapping manuel des outils représente ~150 lignes de code fragile qui reproduit ce que le système de plugins ADK fait nativement. C'est la principale source de complexité accidentelle et de bugs potentiels.

**Independent Test** : Exécuter une mission complète avec `ADK_USE_NATIVE_PLUGINS=true` — le fichier d'audit produit par agent doit être structurellement identique à la capture golden de référence.

**Acceptance Scenarios** :

1. **Given** `ADK_USE_NATIVE_PLUGINS=true`, **When** un outil est appelé par un agent, **Then** les comportements transversaux s'exécutent dans l'ordre canonique (Guardrails → Resilience → Audit → Activity → Memory → Isolation → Autonomy → ErrorHandler).
2. **Given** un outil lève une exception, **When** le gestionnaire d'erreurs transversal est déclenché, **Then** l'erreur est capturée proprement sans être convertie en message opaque renvoyé au LLM.
3. **Given** un plugin d'isolation bloque une action cross-env, **When** l'outil est invoqué, **Then** l'agent reçoit un refus explicite et la mission continue sans crash.
4. **Given** un outil nécessite des paramètres techniques (URL Prometheus, proxy, kubeconfig), **When** le LLM ne les fournit pas, **Then** ils sont injectés automatiquement depuis la configuration de l'environnement de la mission.
5. **Given** `ADK_USE_NATIVE_PLUGINS=false` (valeur par défaut), **When** une mission est déclenchée, **Then** l'ancienne chaîne de plugins custom s'active et le comportement est identique au baseline.

---

### User Story 3 — Opérateur : observabilité automatique sans code d'instrumentation custom (Priority: P2)

En tant qu'opérateur de la plateforme, je veux que les traces et métriques des appels d'outils et d'invocations LLM soient exportées automatiquement, sans maintenir de code d'instrumentation custom, afin de disposer de métriques exploitables dans le backend d'observabilité.

**Why this priority** : Le plugin OTel actuel est un stub no-op qui ne produit aucune métrique. Adopter un plugin natif élimine ce code sans valeur et apporte immédiatement des métriques utilisables.

**Independent Test** : Déclencher une mission et interroger le endpoint de métriques — les métriques de durée d'opération des agents et d'usage de tokens doivent apparaître dans les 60 secondes après la fin de la mission.

**Acceptance Scenarios** :

1. **Given** l'instrumentation OTel est activée, **When** un outil est exécuté par un agent, **Then** une trace contenant le nom de l'outil, sa durée et son statut est exportée.
2. **Given** un appel LLM est effectué, **When** la réponse est reçue, **Then** les métriques d'usage de tokens (input/output) sont enregistrées.
3. **Given** le plugin OTel custom supprimé, **When** la plateforme démarre, **Then** aucune exception de plugin manquant n'est levée.

---

### User Story 4 — Mainteneur : orchestration parallèle native des 3 agents experts (Priority: P2)

En tant que mainteneur, je veux que les 3 agents experts soient orchestrés par une primitive native d'ADK, afin que le code d'orchestration soit cohérent avec sa documentation et que les traces de parallélisme soient visibles dans le système d'observabilité.

**Why this priority** : L'orchestrateur documente "ParallelAgent(3 experts)" mais utilise `asyncio.gather` avec un stagger artificiel. Corriger cette incohérence améliore la lisibilité et fournit un meilleur tracing.

**Independent Test** : Exécuter une mission complète avec `ADK_USE_PARALLEL_AGENT=true` — les 3 rapports d'experts doivent être produits et le rapport de consolidation doit référencer les 3 sources.

**Acceptance Scenarios** :

1. **Given** `ADK_USE_PARALLEL_AGENT=true`, **When** une mission est déclenchée, **Then** les 3 agents experts démarrent sans délai artificiel entre eux.
2. **Given** les 3 agents s'exécutent en parallèle, **When** chacun termine, **Then** leurs sorties sont disponibles pour l'agent de consolidation via le contexte partagé.
3. **Given** l'orchestration parallèle native est active, **When** les traces sont consultées, **Then** un span parent unique contient 3 spans enfants correspondant aux 3 experts.
4. **Given** le bloc d'injection du token GKE dans l'orchestrateur, **When** l'orchestration démarre, **Then** ce bloc s'exécute avant le lancement des agents parallèles, sans modification de son comportement.

---

### User Story 5 — Architecte : base ADK 2.x pour les fonctionnalités futures (Priority: P3)

En tant qu'architecte de la plateforme, je veux que la classe de base des agents hérite des fondations d'ADK 2.x, afin d'ouvrir l'accès aux capacités de workflow avancé (intervention humaine, retries, nœuds dynamiques) pour les futures évolutions.

**Why this priority** : C'est l'investissement le plus risqué. Il est positionné en dernier pour que toutes les autres workstreams consolident la stabilité avant cette rupture.

**Independent Test** : Exécuter la suite complète des scénarios golden (alertmanager + Jira) et comparer les BRIEF.md produits avec la baseline ADK 1.x — les outputs doivent être sémantiquement équivalents avec la même politique de langue.

**Acceptance Scenarios** :

1. **Given** ADK 2.x est le runtime, **When** une mission est déclenchée, **Then** le pipeline complet (Intake → Experts → Consolidator → PostMortem) s'exécute sans erreur.
2. **Given** des missions ont été créées avec ADK 1.x, **When** la plateforme est mise à jour vers 2.x, **Then** les sessions existantes restent lisibles.
3. **Given** la politique de langue française (ADR-005), **When** un rapport est produit par ADK 2.x, **Then** le contenu du BRIEF.md est en français, identique au format de la baseline.
4. **Given** les variables de contexte de mission injectées dans l'état de session, **When** le LLM traite le prompt, **Then** la substitution produit un résultat identique à la baseline (aucune dérive de contenu).

---

### Edge Cases

- Que se passe-t-il si un plugin lève une exception dans le hook `before-tool` ? La mission doit échouer proprement avec un message d'erreur dans l'audit, sans crash silencieux.
- Comment le système gère-t-il la non-disponibilité temporaire d'un des 3 agents parallèles ? Les 2 autres continuent, le consolidator signale l'agent manquant dans le rapport.
- Que se passe-t-il si `ADK_USE_NATIVE_PLUGINS=false` après que WS-2 est déployée ? La plateforme retombe sur l'ancienne chaîne de plugins custom sans régression.
- Comment les sessions golden ADK 1.x sont-elles gérées après migration ADK 2.x ? Les sessions antérieures à ADK 1.28 doivent être invalidées proprement — celles de 1.28+ restent lisibles.
- Que se passe-t-il si un outil du toolkit déclare des paramètres optionnels avec des valeurs par défaut ? L'injection automatique ne doit pas écraser les valeurs déjà fournies par le LLM.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001** : La plateforme DOIT démarrer sans aucune modification dynamique du runtime ADK — suppression du patch de démarrage dans `api/main.py`.
- **FR-002** : Les 9 comportements transversaux DOIVENT être enregistrés via le système de plugins natif ADK et exécutés dans l'ordre canonique défini.
- **FR-003** : Le code de wrapping manuel des outils dans `BaseAgent` (~150 lignes) DOIT être supprimé — les hooks natifs ADK prennent en charge les callbacks pre/post-outil.
- **FR-004** : L'injection automatique des paramètres techniques (`prom_url`, `proxy_url`, `kubeconfig`) depuis la configuration d'environnement DOIT continuer à fonctionner via un plugin dédié.
- **FR-005** : Les outils du toolkit DOIVENT être déclarés avec un nom et une description explicites, sans renommage par mutation d'attribut interne.
- **FR-006** : Les métriques de durée d'opération et d'usage de tokens DOIVENT être exportées automatiquement pour chaque invocation d'agent, sans code d'instrumentation manuel dans la plateforme.
- **FR-007** : Les 3 agents experts DOIVENT être lancés via une primitive d'orchestration parallèle native d'ADK, sans délai artificiel ni gestion manuelle de la concurrence.
- **FR-008** : La politique de langue française (ADR-005) DOIT être préservée à l'identique dans tous les outputs des agents après migration — aucune dérive de contenu autorisée.
- **FR-009** : Le bloc d'injection du token GKE dans l'orchestrateur NE DOIT PAS être modifié par cette migration.
- **FR-010** : Chaque workstream comportementale (plugins natifs, parallélisme natif) DOIT être activable/désactivable via une variable d'environnement dédiée pendant la transition.
- **FR-011** : La classe de base des agents DOIT hériter des fondations ADK 2.x, en remplacement du loop manuel d'événements.
- **FR-012** : La substitution des variables de contexte dans les prompts DOIT utiliser le mécanisme natif de l'état de session ADK, sans code de substitution personnalisé.
- **FR-013** : 3 captures golden de missions DOIVENT être produites avant toute modification de code et servir de référence de non-régression pour toutes les workstreams.
- **FR-014** : La branche `main` DOIT rester déployable à tout moment — chaque workstream est mergeable indépendamment après validation des captures golden.
- **FR-015** : L'adaptateur RAG (WS-7, stretch) DOIT envelopper l'implémentation pgvector existante sans migrer les données vers un service managé externe.

### Key Entities

- **WorkstreamGate** : Variable d'environnement associée à une workstream, permettant la bascule progressive entre ancien et nouveau comportement (`ADK_USE_NATIVE_PLUGINS`, `ADK_USE_PARALLEL_AGENT`).
- **GoldenCapture** : Snapshot d'une mission complète (prompts, appels d'outils, BRIEF.md, KB card, fichier d'audit) servant de référence de non-régression.
- **PluginRegistry** : Liste ordonnée des comportements transversaux enregistrés sur le Runner ADK — remplace l'instanciation manuelle de la chaîne de plugins custom.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001** : La plateforme démarre en moins de 10 secondes sans aucun message d'avertissement lié à des modifications dynamiques du framework sous-jacent.
- **SC-002** : Les 3 captures golden comparées avant/après chaque workstream produisent un diff nul sur les structures de données (fichier d'audit, KB card JSON, BRIEF.md frontmatter) et un diff sémantiquement équivalent pour le texte généré par LLM.
- **SC-003** : Le volume de code de wrapping supprimé est supérieur à 120 lignes dans la classe de base des agents, sans ajout de code de compensation équivalent ailleurs.
- **SC-004** : Les métriques d'observabilité (durée opération, usage tokens) sont disponibles dans le backend de métriques dans les 60 secondes suivant la fin d'une mission.
- **SC-005** : Le temps d'exécution total d'une mission n'est pas dégradé de plus de 5% après migration complète (WS-1 à WS-6) par rapport au baseline ADK 1.33.
- **SC-006** : 100% des missions déclenchées sur la branche de migration produisent un rapport BRIEF.md et une KB card valides, sans erreur fatale de pipeline.
- **SC-007** : Chaque workstream (WS-1 à WS-6) est réversible par un seul revert de commit sans impact sur les workstreams adjacentes.

---

## Assumptions

- La branche `main` est opérationnelle et testable sur l'environnement LAB avant le début de la migration.
- ADK 1.35.x est rétrocompatible avec les sessions créées en 1.33 — aucune migration de données de session requise pour WS-1.
- ADK 2.x lit les sessions créées par ADK 1.28+ — les missions en cours au moment du saut 2.x peuvent nécessiter d'être terminées ou invalidées manuellement.
- Les outils du toolkit n'ont pas d'effets de bord liés au renommage par mutation d'attribut interne dans leur propre code.
- ~~`ADK_USE_NATIVE_PLUGINS=false` (valeur par défaut pendant la transition) active la chaîne de plugins legacy et laisse la plateforme dans son état pré-migration.~~ *(flags supprimés — Phase 8 cleanup 2026-06-11)*
- Le RAG pgvector existant (WS-7 stretch) n'est PAS migré vers un service managé externe — l'implémentation reste sur PostgreSQL local.
- Les fonctionnalités MCP, A2A, Live API et BigQuery Analytics sont hors périmètre de cette migration.
- Cette migration est réalisée en solo sur une branche dédiée — aucune coordination d'équipe requise pour les merges.

---

## Statut post-migration

**Date de bascule** : 2026-06-11

La migration Google ADK 1.33 → 2.x est **complète**. Le mode dual (feature flags `ADK_USE_NATIVE_PLUGINS` / `ADK_USE_PARALLEL_AGENT`) a été introduit comme filet de sécurité lors de la transition, puis retiré lors de la Phase 8 (cleanup).

**État final** :
- La plateforme tourne **exclusivement sur ADK 2.x natif** — aucun code legacy `PluginChain`, `Plugin` ABC, `_wrap_tool`, `default_plugin_chain`.
- `build_plugin_list()` est la seule factory de plugins — retourne une `list[BasePlugin]` pour `Runner(plugins=[...])`.
- Les 3 agents experts (`KafkaStrimziExpertAgent`, `K8sGcpSreAgent`, `PromAlertTriageAgent`) utilisent `FunctionTool(fn)` directement.
- Le fan-out parallèle est `asyncio.gather()` sans stagger — `ParallelAgent` ADK natif reporté à WS-6 (si `BaseAgent→BaseNode` est requis).
- `AutoTracingPlugin` est actif en dernier plugin dans la chaîne — traces OTel exportées automatiquement.
- `kafka-agent-toolkit` n'est **pas impacté** : zero import ADK, docstrings déjà compatibles `FunctionTool(fn)`.

**WS-6 (BaseNode) et WS-7 (PgVectorMemoryService)** restent en statut **STRETCH** — non requis pour le bon fonctionnement de la plateforme sur ADK 2.x.
