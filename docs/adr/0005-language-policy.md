# ADR-005 — Politique de langue des sorties agents (PLATFORM_LANG)

**Statut** : Accepté  
**Date** : 2026-05-18  
**Auteur** : infra-ops

---

## Contexte

La plateforme est déployée en interne. Les équipes SRE/InfraOps qui consomment les sorties (`audit.md`, `BRIEF.md`, rapports d'agents, cartes KB) sont francophones. Les analyses produites initialement en anglais créaient une friction inutile à la lecture.

Contrainte : les modèles LLM (Gemini 2.5) produisent un raisonnement de meilleure qualité en anglais sur les arbres de décision techniques (URP/ISR/lag/PVC). Forcer le français sur l'ensemble du traitement dégraderait la précision des diagnostics.

## Décision

Adopter une **politique bilingue asymétrique** :

- **Raisonnement interne** : anglais (chain-of-thought, appels outils, décisions algorithmiques)
- **Sorties finales** (Markdown visible par l'utilisateur) : français professionnel
- **Termes techniques** conservés en anglais : `broker`, `partition`, `topic`, `lag`, `ISR`, `URP`, `throughput`, `leader/follower`, `KRaft`, `rolling restart`, `log compaction`, `pod`, `node`, `PVC`, `namespace`, `deployment`, `statefulset`, `P99`, `GC pause`, `CFS throttling`
- **Données structurées** (frontmatter YAML, noms de champs, slugs, requêtes PromQL) : anglais

## Mécanisme d'implémentation

Variable d'environnement `PLATFORM_LANG` (valeur : `fr` ou `en`, défaut : `en`).

Quand `PLATFORM_LANG=fr`, `agents/base.py` préfixe chaque `system_prompt` avec un bloc de politique de langue (`_FR_LANGUAGE_POLICY`) avant de l'envoyer à l'agent ADK.

Les templates des sections de sortie dans les SKILL.md sont rédigés en français pour guider la structure des sorties.

## Conséquences

### Positives
- Sorties lisibles nativement pour les équipes opérationnelles
- Qualité d'analyse préservée (raisonnement EN)
- Rollback immédiat possible (`PLATFORM_LANG=en` ou supprimer la variable)
- Toggle utilisable pour A/B testing qualité

### Négatives / Risques
- Légère augmentation de la longueur du system_prompt (~15 lignes)
- Possibilité que le modèle mélange les langues sur des formulations ambiguës → à surveiller en production

## Critère de retrait

Si un modèle futur supporte nativement la politique de langue au niveau API (paramètre `output_language`), migrer vers cette option et supprimer le bloc `_FR_LANGUAGE_POLICY` de `agents/base.py`.

## Fichiers impactés

- `agents/base.py` — injection du bloc `_FR_LANGUAGE_POLICY`
- `agents/*/SKILL.md` — templates de sections de sortie en français
- `agents/post_mortem_analyst/agent.py` — `_build_card_body()` placeholders traduits
