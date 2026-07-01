# Quickstart — Scénarios de test 013-hermes-ui-refonte

## Prérequis

```bash
# 1. Back-end démarré
uv run uvicorn api.main:app --reload

# 2. Front-end démarré
cd web && pnpm dev

# 3. DB avec au moins un trigger et une mission de test
# (Utiliser les fixtures ci-dessous)
```

---

## Scénario 1 — OpsStrip + AttentionCard (P1)

### Préparer les données

```sql
-- Forcer un trigger DEAD pour déclencher AttentionCard
UPDATE triggers 
SET last_error = 'DEAD: max attempts reached', attempts = 3
WHERE id = (SELECT id FROM triggers WHERE matched = true LIMIT 1);
```

### Tester

1. Ouvrir `http://localhost:3000` — vérifier que la barre OpsStrip s'affiche en haut
2. Observer : `worker_count`, `queue_depth`, badge "Attention" ou "Critique"
3. La carte AttentionCard doit apparaître (dead_count >= 1)
4. Cliquer le lien dans AttentionCard → redirige vers `/missions?view=kanban`
5. Rétablir le trigger : `UPDATE triggers SET last_error = NULL, attempts = 0 WHERE ...`
6. Attendre ≤ 5s → AttentionCard disparaît, badge passe à "Opérationnel"

### Critères de succès

- [x] OpsStrip visible sur toutes les pages (dashboard, missions, monitoring, etc.)
- [x] Rafraîchissement automatique visible (les chiffres changent sans recharger la page)
- [x] AttentionCard apparaît/disparaît selon le statut en DB

---

## Scénario 2 — Vue Kanban des missions (P2)

### Préparer les données

```sql
-- Trigger en attente
INSERT INTO triggers (tenant, source, external_id, payload, matched)
VALUES ('enterprise', 'alertmanager', 'test-kanban-1', '{}', true);

-- Trigger réservé (simuler un worker actif)
INSERT INTO triggers (tenant, source, external_id, payload, matched, claimed_at, claimed_by, attempts)
VALUES ('enterprise', 'alertmanager', 'test-kanban-2', '{}', true, now(), 'worker-test-0', 1);

-- Trigger en échec
INSERT INTO triggers (tenant, source, external_id, payload, matched, last_error, attempts)
VALUES ('enterprise', 'alertmanager', 'test-kanban-3', '{}', true, 'DEAD: too many failures', 3);
```

### Tester

1. Ouvrir `http://localhost:3000/missions`
2. Cliquer le basculeur "Kanban" (haut droit de la page)
3. Vérifier les 4 colonnes en français : "En attente" / "Réservée" / "Terminée" / "En échec"
4. Vérifier que les cartes de test apparaissent dans les bonnes colonnes
5. Sur la colonne "En échec" : cliquer "Relancer" sur la carte test-kanban-3
6. Observer que la carte migre vers "En attente" au prochain rafraîchissement (≤ 8s)
7. Cliquer "Tableau" → revenir à la vue liste (aucune régression)

### Critères de succès

- [x] 4 colonnes affichées avec libellés français
- [x] Cartes de test dans les bonnes colonnes
- [x] Bouton "Relancer" visible uniquement sur la colonne "En échec"
- [x] POST /v1/triggers/{id}/retry appelé (vérifier dans les logs back-end)
- [x] Basculeur Table/Kanban fonctionne (les deux vues coexistent)

---

## Scénario 3 — Cycle de vie d'une mission (P3)

### Préparer les données

```sql
-- Mission avec trigger associé ayant subi 2 tentatives
SELECT mission_id FROM missions LIMIT 1;
-- Note l'ID de mission renvoyé

UPDATE triggers 
SET claims = 2, claimed_at = now() - interval '5 minutes', claimed_by = 'worker-test-0'
WHERE mission_id = '<mission_id>';
```

### Tester

1. Ouvrir `http://localhost:3000/missions/<mission_id>`
2. Scroller jusqu'à la section "Cycle de vie"
3. Vérifier la frise : "Reçu" → "Réservé" → "Mission créée" → "Traité"
4. Vérifier : timestamp de chaque étape, nombre de tentatives affiché (2)
5. Pour une mission en cours (OPEN) : laisser la page ouverte → observer la mise à jour automatique (≤ 3s)

### Critères de succès

- [x] Frise chronologique visible avec les horodatages
- [x] Nombre de tentatives correct
- [x] `claimed_by` (worker ID) visible
- [x] Mise à jour automatique pour les missions en cours

---

## Scénario 4 — Surveillance temps réel (P4)

### Tester

1. Ouvrir `http://localhost:3000/monitoring`
2. Vérifier que les graphiques s'affichent (Recharts)
   - Line chart : profondeur de file + en cours (axe temps)
   - Bar chart : p50/p95/p99 en secondes
   - Pie chart : résultats 24h
3. Créer de l'activité (déclencher un trigger) et observer la mise à jour automatique (≤ 10s)
4. Scroller en bas → vérifier que le journal d'activité est toujours présent
5. Vérifier l'absence du polling `limit:1` dans les logs réseau (Network tab du navigateur)

### Critères de succès

- [x] 3 graphiques affichés et mis à jour automatiquement
- [x] Journal d'activité conservé en bas de page
- [x] Aucun appel `/v1/missions?limit=1` ou `/v1/triggers?limit=1` dans le réseau

---

## Scénario 5 — Catalogue Agents & Skills (P5)

### Tester

1. Ouvrir `http://localhost:3000/admin/agents`
2. Vérifier 6 cartes d'agents (intake, kafka_strimzi_expert, k8s_gcp_sre, prom_alerts_triage, evidence_consolidator, post_mortem_analyst)
3. Chaque carte doit afficher : nom, description (depuis SKILL.md frontmatter), version
4. Ouvrir `http://localhost:3000/admin/skills`
5. Vérifier la liste des compétences avec filtres par catégorie
6. Filtrer par "infrastructure" → vérifier que seuls les agents k8s/GCP s'affichent

### Critères de succès

- [x] 6 agents listés
- [x] Description correcte (lue depuis `agents/*/SKILL.md`)
- [x] Filtres par catégorie fonctionnels
- [x] Aucune erreur 500 (endpoint lit bien les SKILL.md depuis le filesystem)

---

## Vérification de non-régression

```bash
# Back-end : 170 tests unitaires doivent passer
cd /mnt/c/CARREF~1/PHENIX~1/workspace_ai/kafka-agentic-platform
uv run pytest tests/unit/ -q --tb=short

# Front-end : build sans erreur TypeScript
cd web
npx tsc --noEmit  # 0 erreur TypeScript attendue
pnpm build        # build production sans erreur

# Test manuel des pages existantes (non-régression)
# → /triggers : table de triggers avec onglets "Tous reçus / Ignorés"
# → /kb : grille de cartes KB
# → /settings/filters : CRUD règles de filtrage
# → /settings/tenants : gestion infrastructure
```

---

## Données de test utiles

```bash
# Créer rapidement des données de test via l'API
curl -X POST http://localhost:8000/v1/triggers \
  -H "Content-Type: application/json" \
  -d '{"tenant": "enterprise", "source": "alertmanager", "external_id": "test-001", "payload": {}}'

# Simuler un DEAD trigger (pour tester AttentionCard + Kanban En échec)
psql $DATABASE_URL -c "
  UPDATE triggers 
  SET last_error = 'DEAD: test scenario', attempts = 3 
  WHERE external_id = 'test-001';
"

# Relancer via API
curl -X POST http://localhost:8000/v1/triggers/<uuid>/retry
```
