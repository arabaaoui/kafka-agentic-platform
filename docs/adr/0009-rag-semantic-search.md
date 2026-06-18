# ADR-009 — RAG Semantic Search & Agent Auto-Learning Loop

**Statut** : Accepted — 2026-05-20  
**Spec** : `specs/009-rag-autolearning/`

---

## Contexte

La recherche keyword-based (`KBIndexLegacy`) ne retrouvait pas les cartes KB lorsque la formulation
de la requête différait du vocabulaire exact des cartes. Objectif : remplacer par une recherche
sémantique bilingue (FR/EN) qui indexe également les audits passés pour alimenter la boucle
d'auto-apprentissage.

---

## Décision

- **Modèle d'embeddings** : `intfloat/multilingual-e5-small` (384 dimensions, CPU-only, bilingue)
- **Stockage vectoriel** : extension `pgvector` sur PostgreSQL existant (pas de service additionnel)
- **Chunking** : split H2 → sliding window 512 tokens / 10 % overlap
- **Boucle d'apprentissage** : `post_mortem_analyst.finalize()` ingère automatiquement chaque nouvel
  audit et chaque carte KB créée/mise à jour

---

## Déploiement

### Pré-requis PostgreSQL

L'extension `pgvector` doit être installée sur le cluster PostgreSQL **avant** la migration Alembic.

```bash
# Debian/Ubuntu
apt-get install postgresql-15-pgvector

# Ou via image Docker (ajouter au Dockerfile de la DB)
FROM postgres:15
RUN apt-get update && apt-get install -y postgresql-15-pgvector
```

Puis dans psql :
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

La migration Alembic (`add_rag_tables`) le fait automatiquement via `op.execute(...)` mais
l'extension doit être disponible.

### Migration Alembic

```bash
uv run alembic upgrade head
```

Vérifie que les tables `kb_chunks` et `audit_chunks` ont bien été créées avec les index HNSW.

### Modèle d'embeddings

Le modèle est téléchargé depuis Hugging Face Hub au premier appel (lazy loading). En production,
pré-charger dans un volume persistant pour éviter le téléchargement au démarrage :

```dockerfile
# Dans le Dockerfile de l'application :
ARG EMBEDDING_MODEL_NAME=intfloat/multilingual-e5-small
ARG EMBEDDING_MODEL_PATH=/models/multilingual-e5-small
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('${EMBEDDING_MODEL_NAME}').save('${EMBEDDING_MODEL_PATH}')"
```

Variables d'environnement à configurer (voir `.env.example`) :
```
EMBEDDING_MODEL_NAME=intfloat/multilingual-e5-small
EMBEDDING_MODEL_PATH=/models/multilingual-e5-small
RAG_SCOPE=kb,audit
```

### Bootstrap de l'index (première mise en production)

Après migration, indexer tout l'historique existant :

```bash
uv run python scripts/reindex_all.py
```

Le script est idempotent. Il peut être relancé sans risque.

### Maintien en cohérence post-déploiement

| Déclencheur | Action automatique |
|-------------|-------------------|
| `POST /{mission_id}/finalize` | Ingestion audit + carte KB (si créée/MAJ) |
| Modification manuelle d'une carte KB | Relancer `scripts/reindex_all.py` |

---

## Conséquences

- Ajout de ~180 MB de dépendances Python (`sentence-transformers`, `torch` CPU)
- Augmentation de la RAM du pod applicatif (~300 MB pour le modèle en mémoire)
- Latence de recherche : < 50 ms pour 10 000 chunks (benchmark HNSW cosine sur pgvector 0.7)
- Fallback : si pgvector ou le modèle est indisponible, `RAGIndex.search()` retourne `[]` sans
  planter la mission
