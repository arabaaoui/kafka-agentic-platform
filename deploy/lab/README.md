# Phenix Lab — Stack Kafka/K3s locale

Stack de test locale pour le développement et la validation des agents.
Les manifestes Kubernetes (Strimzi KRaft) et les scripts de provisioning
sont ici. Les services Docker (`phenix-k8s`, `phenix-provisioner`) sont
définis dans `deploy/docker-compose.yml` et démarrent avec le reste de la plateforme.

## Architecture

| Composant | Technologie | Version | Rôle |
|:---|:---|:---|:---|
| **Orchestrateur K8s** | K3s | v1.31 | Cluster Kubernetes léger dans Docker |
| **Kafka Operator** | Strimzi | 0.45.1 | Gestion du cycle de vie Kafka |
| **Broker Kafka** | Apache Kafka | 3.9.1 | Mode **KRaft** (sans Zookeeper) + NodePools |
| **Monitoring** | Prometheus Community | latest | Métriques Kafka et infra |
| **Alerting** | Alertmanager Community | latest | Routage alertes vers l'agent |

## Démarrage

```bash
# Depuis la racine du repo
cd kafka-agentic-platform

# Démarrer toute la stack (platform + lab K3s)
docker compose -f deploy/docker-compose.yml up -d

# Vérifier que K3s et le provisioner sont prêts (~3-5 min)
docker logs -f phenix-lab-provisioner
# Attendre "✅ Phenix Lab is ready!"
```

## Ports exposés par le lab

| Port | Service |
|:-----|:--------|
| `6443` | Kubernetes API Server |
| `30090` | Prometheus |
| `30092` | Kafka bootstrap (NodePort externe) |
| `30093` | Alertmanager |

## Commandes d'exploitation

Le container `phenix-lab-provisioner` sert de jumpbox kubectl :

```bash
# État général du cluster
docker exec phenix-lab-provisioner kubectl get pods -A

# Santé du cluster Kafka
docker exec phenix-lab-provisioner kubectl get kafka phenix-lab -n kafka -o wide

# Logs d'un broker
docker exec phenix-lab-provisioner kubectl logs -n kafka phenix-lab-broker-0 --tail=50

# Vérifier les PrometheusRules
docker exec phenix-lab-provisioner kubectl get prometheusrule -A

# Accès Prometheus (port-forward depuis le container)
docker exec phenix-lab-provisioner kubectl port-forward svc/prom-prometheus-server 9090:80 -n monitoring &
# Puis ouvrir http://localhost:9090
```

## Injection de données de test (simulation lag)

```bash
# Créer topic + injecter 1000 messages + consommer 500 (génère du lag)
./deploy/lab/kafka-filler.sh
```

## Sécurité

1. **Isolation kubeconfig** : K3s génère `/output/kubeconfig.yaml` dans un volume Docker partagé. Le backend monte ce volume (`k3s_output:/app/kube_conf`). Aucun accès aux kubeconfig GKE personnels.
2. **Wrapper k-exec** : Les outils agent passent par `kubectl get/list/describe/logs/top` uniquement — `delete/patch/apply` sont bloqués par l'`AutonomyPlugin` L2.
3. **Mode lecture seule v0** : Aucune action mutante possible sans intervention humaine explicite.

## Fichiers du lab

| Fichier | Rôle |
|:--------|:-----|
| `kafka-kraft-lab.yaml` | Manifestes Strimzi : KafkaNodePool (controllers + brokers) + Kafka CRD |
| `provisioner.sh` | Script d'init : install Strimzi 0.45.1, déploiement Kafka, Prometheus/Alertmanager |
| `kafka-filler.sh` | Injection de données de test (topic + messages + lag) |
| `kind-config.yaml` | Config Kind alternative (non utilisé en v0 — K3s privilégié) |
