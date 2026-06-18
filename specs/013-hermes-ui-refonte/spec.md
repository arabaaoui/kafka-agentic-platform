# Spécification Fonctionnelle : Refonte UI inspirée Hermes-Workspace

**Branche** : `013-hermes-ui-refonte`  
**Date** : 2026-06-15  
**Statut** : Brouillon  
**Langue cible** : Toute l'interface utilisateur en français

---

## Scénarios Utilisateurs & Tests *(obligatoire)*

### Histoire Utilisateur 1 — Tableau de bord opérationnel en temps réel (Priorité : P1)

En tant qu'opérateur de permanence, je veux voir en permanence l'état de santé de la plateforme (workers actifs, profondeur de file, missions en échec) dès que j'ouvre l'application, afin de détecter immédiatement un problème sans naviguer entre plusieurs pages.

**Pourquoi P1** : C'est la première information consultée lors d'une prise de permanence. Aujourd'hui, le tableau de bord affiche `--` pour toutes les métriques clés — la moindre anomalie reste invisible jusqu'à ce que quelqu'un cherche activement.

**Test indépendant** : Ouvrir l'application et vérifier qu'une barre de statut affiche le nombre de workers, la profondeur de file, et un badge de santé global. Forcer une mission en état d'échec dans la base et vérifier qu'une carte d'alerte apparaît automatiquement dans les 10 secondes.

**Scénarios d'acceptation** :

1. **Étant donné** que la plateforme tourne normalement, **quand** l'opérateur ouvre n'importe quelle page, **alors** une barre en haut de l'écran affiche : nombre de workers actifs, profondeur de file d'attente, âge du déclencheur le plus ancien en attente, et nombre de missions en échec.
2. **Étant donné** qu'au moins une mission est en état « En échec », **quand** la barre est rafraîchie automatiquement, **alors** une carte d'alerte visible indique le problème avec un lien vers les missions concernées.
3. **Étant donné** que la file dépasse 50 éléments ou qu'un déclencheur attend depuis plus de 10 minutes, **quand** cet état persiste, **alors** la carte d'alerte apparaît avec un niveau d'urgence approprié (orange ou rouge).
4. **Étant donné** que tout est normal (file vide, zéro mission en échec), **quand** l'opérateur regarde la barre, **alors** un badge vert « Opérationnel » s'affiche sans alerte.

---

### Histoire Utilisateur 2 — Vue Kanban des missions (Priorité : P2)

En tant qu'opérateur, je veux visualiser les missions sous forme de tableau Kanban avec des colonnes correspondant à leur état (En attente / Réservée / Terminée / En échec), afin de comprendre d'un coup d'œil où en est chaque mission et agir directement sur les missions bloquées.

**Pourquoi P2** : La vue tableau actuelle ne permet pas de distinguer visuellement les missions en cours des missions bloquées. C'est la prochaine source de valeur la plus immédiate pour réduire le temps de réaction.

**Test indépendant** : Naviguer vers « Missions », activer la vue Kanban, vérifier que 4 colonnes s'affichent avec les missions bien distribuées. Relancer une mission en échec depuis sa carte et vérifier qu'elle migre vers la colonne « En attente ».

**Scénarios d'acceptation** :

1. **Étant donné** que l'opérateur est sur la page Missions, **quand** il bascule sur la vue Kanban, **alors** 4 colonnes s'affichent en français : « En attente », « Réservée », « Terminée », « En échec » — chacune avec ses missions sous forme de cartes.
2. **Étant donné** une mission dans la colonne « En échec », **quand** l'opérateur clique sur « Relancer », **alors** la mission est remise en file et apparaît dans « En attente » au prochain rafraîchissement automatique.
3. **Étant donné** une mission dans n'importe quelle colonne, **quand** l'opérateur clique sur son titre, **alors** il est redirigé vers la page détail de cette mission.
4. **Étant donné** une mission terminée, **quand** l'opérateur clique sur « Finaliser » ou « Publier sur Jira », **alors** l'action s'exécute avec le même comportement que dans la vue tableau.
5. **Étant donné** que l'opérateur préfère la vue tableau, **quand** il clique sur le basculeur « Tableau », **alors** la vue liste existante s'affiche sans modification ni régression.

---

### Histoire Utilisateur 3 — Suivi du cycle de vie d'une mission (Priorité : P3)

En tant qu'opérateur post-incident, je veux voir la chronologie complète d'une mission (de sa réception à sa clôture) incluant les tentatives successives, le worker responsable, et les erreurs éventuelles, afin de comprendre les rechutes et diagnostiquer les problèmes récurrents.

**Pourquoi P3** : La page de détail actuelle affiche l'audit IA mais pas le cycle de vie au niveau infrastructure (tentatives, délais de réservation, worker assigné). Cette information est indispensable pour les post-mortems.

**Test indépendant** : Ouvrir la page d'une mission ayant subi plusieurs tentatives et vérifier que la section « Cycle de vie » présente une frise chronologique avec au minimum : date de réception, date de réservation, date de création de la mission, nombre de tentatives.

**Scénarios d'acceptation** :

1. **Étant donné** une page de détail de mission, **quand** l'opérateur consulte la section « Cycle de vie », **alors** une frise chronologique affiche les étapes disponibles : Reçu, Réservé, Mission créée, Traité — avec les horodatages.
2. **Étant donné** une mission ayant nécessité plusieurs tentatives, **quand** l'opérateur consulte le cycle de vie, **alors** le nombre de tentatives et le motif du dernier échec sont visibles.
3. **Étant donné** une mission en cours de traitement, **quand** l'opérateur consulte la page, **alors** les informations se mettent à jour automatiquement toutes les quelques secondes.

---

### Histoire Utilisateur 4 — Surveillance des performances en temps réel (Priorité : P4)

En tant qu'opérateur, je veux consulter une page de surveillance qui affiche des graphiques d'évolution de la profondeur de file, du débit, et de la latence des missions, afin de détecter une dégradation progressive avant qu'elle ne devienne critique.

**Pourquoi P4** : La page Surveillance actuelle ne montre que 4 compteurs instantanés sans tendance ni graphique. Une montée lente de la file passe inaperçue.

**Test indépendant** : Ouvrir la page « Surveillance » et vérifier que des graphiques s'affichent et se mettent à jour automatiquement avec des données de profondeur de file, durée de traitement et répartition des résultats.

**Scénarios d'acceptation** :

1. **Étant donné** que l'opérateur ouvre la page « Surveillance », **quand** la page charge, **alors** des graphiques affichent : évolution de la profondeur de file dans le temps, missions en cours, durée de traitement (rapide/médian/lent), répartition des résultats des dernières 24h (succès / échec / mort).
2. **Étant donné** que les graphiques sont affichés, **quand** le temps passe, **alors** les courbes se mettent à jour automatiquement sans intervention.
3. **Étant donné** que l'opérateur fait défiler la page, **quand** il atteint le bas, **alors** le journal d'activité récent est toujours accessible (comportement actuel conservé).

---

### Histoire Utilisateur 5 — Catalogue des agents et compétences (Priorité : P5)

En tant que référent technique ou nouvel arrivant, je veux consulter la liste des agents IA de la plateforme et leurs compétences (outils disponibles), afin de comprendre rapidement ce que la plateforme peut faire sans lire le code source.

**Pourquoi P5** : Aucune visibilité aujourd'hui sur les agents actifs et leurs capacités. Nécessaire pour l'intégration des nouveaux membres et pour les démonstrations.

**Test indépendant** : Ouvrir la page « Agents » et vérifier que chaque agent apparaît sous forme de fiche avec ses outils listés. Ouvrir la page « Compétences » et filtrer par catégorie.

**Scénarios d'acceptation** :

1. **Étant donné** une navigation vers « Administration → Agents », **quand** la page charge, **alors** une grille de fiches s'affiche (une par agent actif) avec le nom, le rôle, et les outils disponibles.
2. **Étant donné** la page « Agents », **quand** l'utilisateur consulte une fiche, **alors** les compétences de l'agent sont visibles (ex : kubectl, PromQL, recherche dans la base de connaissances).
3. **Étant donné** une navigation vers « Administration → Compétences », **quand** la page charge, **alors** une liste filtrable par catégorie (infrastructure / données / externe) affiche toutes les compétences avec l'agent associé.

---

### Histoire Utilisateur 6 — Suivi des coûts LLM (Priorité : P6)

En tant que responsable de la plateforme, je veux consulter les coûts d'utilisation du modèle de langage par locataire, environnement et agent, afin de maîtriser les dépenses et identifier les usages anormaux.

**Pourquoi P6** : Fonctionnalité de Phase 3 — conditionnelle à la disponibilité des données de coût via le service de traçabilité.

**Test indépendant** : Ouvrir la page « Coûts » et vérifier qu'un tableau affiche la consommation de tokens et le coût estimé par combinaison locataire/environnement/agent, avec un graphique de tendance sur 7 jours.

**Scénarios d'acceptation** :

1. **Étant donné** une navigation vers « Coûts », **quand** la page charge, **alors** un tableau affiche la consommation (tokens entrants/sortants) et le coût estimé groupé par locataire, environnement et agent.
2. **Étant donné** le tableau des coûts, **quand** l'utilisateur consulte la page, **alors** un graphique de tendance sur 7 jours est visible sous le tableau.
3. **Étant donné** que les données de coût ne sont pas disponibles, **quand** la page tente de charger, **alors** un message explicite informe l'utilisateur et propose un lien vers le service de traçabilité externe.

---

### Cas limites

- Que se passe-t-il si la plateforme back-end est inaccessible ? → Les graphiques et compteurs affichent un état d'erreur explicite en français, sans valeur vide ni message technique.
- Que se passe-t-il si la colonne « En attente » contient plus de 100 missions ? → La colonne Kanban affiche les N premières avec un compteur total visible (ex : « 120 en attente »).
- Que se passe-t-il si l'utilisateur clique deux fois rapidement sur « Relancer » ? → La deuxième action est ignorée ou le bouton est désactivé pendant le traitement (idempotence).
- Que se passe-t-il si une mission est en cours au moment où l'opérateur consulte sa page de détail ? → La page indique clairement que le traitement est en cours et se met à jour automatiquement.
- Que se passe-t-il si les données de coût Langfuse ne sont pas disponibles ? → La page Coûts affiche un message d'indisponibilité et un lien direct vers Langfuse.

---

## Exigences Fonctionnelles *(obligatoire)*

### Exigences fonctionnelles

- **EF-001** : L'interface DOIT afficher en permanence l'état de santé de la plateforme (workers actifs, profondeur de file, missions en échec) sur toutes les pages, avec rafraîchissement automatique.
- **EF-002** : L'interface DOIT alerter visuellement l'opérateur (carte d'alerte visible) dès qu'une mission est en échec ou que la file dépasse un seuil critique.
- **EF-003** : L'interface DOIT proposer une vue Kanban pour les missions, avec 4 colonnes en français correspondant aux états de traitement réels.
- **EF-004** : La vue Kanban DOIT permettre de relancer une mission en échec directement depuis sa carte.
- **EF-005** : La vue Kanban DOIT se mettre à jour automatiquement pour refléter l'état courant des missions.
- **EF-006** : La vue tableau des missions existante DOIT être conservée intégralement (aucune régression sur les colonnes, filtres et actions actuelles).
- **EF-007** : La page de détail d'une mission DOIT afficher le cycle de vie complet avec horodatages et nombre de tentatives.
- **EF-008** : La page de détail d'une mission en cours de traitement DOIT se mettre à jour automatiquement.
- **EF-009** : La page Surveillance DOIT afficher des graphiques d'évolution temporelle de la profondeur de file, du débit de traitement, et de la latence.
- **EF-010** : Les graphiques de surveillance DOIVENT se mettre à jour automatiquement.
- **EF-011** : L'interface DOIT proposer une page de catalogue des agents actifs avec leurs compétences/outils.
- **EF-012** : L'interface DOIT proposer une liste filtrable de toutes les compétences disponibles dans la plateforme.
- **EF-013** : L'interface DOIT afficher les coûts estimés d'utilisation du modèle de langage groupés par locataire, environnement et agent (Phase 3, conditionnel).
- **EF-014** : Tous les libellés, messages, titres de page, noms de colonnes et libellés d'actions DOIVENT être en langue française.
- **EF-015** : Le design system Carrefour (composants et jetons de couleur existants) DOIT être utilisé comme source unique de style — aucune couleur ne doit être codée en dur.
- **EF-016** : Les actions existantes (Finaliser, Publier sur Jira, filtrer les missions, gérer la base de connaissances, gérer les déclencheurs) DOIVENT continuer à fonctionner sans modification ni régression.

### Entités clés

- **Mission** : Tâche d'investigation IA déclenchée par un événement. Possède un statut (ouverte, fermée, partielle) et est liée à un ou plusieurs déclencheurs.
- **Déclencheur** : Événement entrant (alerte, ticket) qui génère une mission. Possède un historique de tentatives de traitement, un état de réservation, et un éventuel motif d'échec.
- **Agent** : Composant IA spécialisé disposant d'un rôle et d'un ensemble de compétences/outils.
- **Compétence/Outil** : Capacité atomique d'un agent (ex : interroger une source de métriques, exécuter une commande d'administration de cluster, rechercher dans la base de connaissances).
- **Métriques de file** : Indicateurs temps réel du système de traitement : profondeur de file, missions en cours, latence, missions en échec.

---

## Critères de Succès *(obligatoire)*

### Résultats mesurables

- **CS-001** : Un opérateur peut évaluer l'état de santé de la plateforme en moins de 5 secondes après ouverture de l'application, sans naviguer entre plusieurs pages.
- **CS-002** : Une mission en échec est visible dans l'interface et peut être relancée en moins de 3 clics depuis la vue Kanban.
- **CS-003** : La page Surveillance affiche des tendances graphiques sur les dernières minutes avec une mise à jour automatique au moins toutes les 10 secondes.
- **CS-004** : Un nouvel arrivant dans l'équipe peut identifier les capacités de la plateforme (agents et compétences) en consultant une seule page, sans lire le code source.
- **CS-005** : La refonte ne cause aucune régression fonctionnelle — toutes les actions existantes continuent de fonctionner identiquement.
- **CS-006** : 100 % des libellés visibles par l'utilisateur sont en français (zéro terme anglais dans l'interface de navigation, les colonnes Kanban, les messages d'état et les boutons d'action).

---

## Hypothèses

- Les utilisateurs sont des ingénieurs DevOps/SRE francophones habitués aux concepts Kafka et Kubernetes — ils préfèrent une interface en français mais tolèrent les identifiants techniques anglais (IDs, codes d'erreur, logs).
- Le nombre d'agents actifs est fixe à court terme (4 agents spécialisés) — aucune création dynamique d'agent via l'UI n'est requise en v1.
- La vue tableau des missions est conservée telle quelle — seule une nouvelle option de vue Kanban est ajoutée, sans modifier les filtres ni les colonnes existants.
- L'action « Relancer » ne s'applique qu'aux missions effectivement en état d'échec terminal — pas aux missions simplement en attente ou réservées.
- Aucun système d'authentification ou de gestion des rôles n'est requis en v1 — toutes les actions sont accessibles à tous les utilisateurs.
- Les données de coût LLM dépendent d'un service de traçabilité externe : si non disponibles, la page Coûts affiche un message d'indisponibilité plutôt qu'une erreur bloquante.
- Le design system (composants de boutons, étiquettes, tiroirs, onglets, notifications) est déjà installé et fonctionnel — seule l'intégration dans les nouvelles pages est requise, pas l'installation du système.
- La connexion réseau entre l'interface et le back-end est fiable — les erreurs de connexion sont des cas exceptionnels à afficher clairement, pas le scénario normal.
