#!/bin/sh
set -e

echo "🚀 [Lab Provisioner] Starting KRaft-enabled Lab..."

# Wait for K3s to write the config file
until [ -f /output/kubeconfig.yaml ]; do
  echo "⏳ Waiting for K3s to generate kubeconfig..."
  sleep 5
done

echo "🔧 Patching kubeconfig for container networking..."
# We patch it early so kubectl commands inside this container work
sed -i 's/127.0.0.1/phenix-k8s-lab/g' /output/kubeconfig.yaml

# Now wait for the API to be reachable
until kubectl cluster-info; do
  echo "⏳ Waiting for K3s API to be ready..."
  sleep 5
done

# --- OPTIMIZATION: Check if already provisioned ---
if kubectl get kafka phenix-lab -n kafka -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null | grep -q "True"; then
  echo "♻️ Kafka is already running and ready. Skipping provisioning."
  echo "✅ [Lab Provisioner] Phenix Lab is ready!"
  tail -f /dev/null
fi
# ------------------------------------------------

echo "📦 [Lab Provisioner] Installing Strimzi Operator 0.45.1..."
kubectl create namespace kafka || true

# Download Strimzi Cluster Operator YAML
curl -ksSL https://github.com/strimzi/strimzi-kafka-operator/releases/download/0.45.1/strimzi-cluster-operator-0.45.1.yaml -o /tmp/strimzi.yaml
kubectl apply -f /tmp/strimzi.yaml -n kafka || true

echo "🔐 [Lab Provisioner] Granting Permissions..."
# Ensure operator has rights for KRaft and Leases
kubectl create clusterrolebinding strimzi-cluster-admin --clusterrole=cluster-admin --serviceaccount=kafka:strimzi-cluster-operator || true

echo "⏳ Waiting for Strimzi CRDs..."
until kubectl get crd kafkas.kafka.strimzi.io; do sleep 5; done
until kubectl get crd kafkanodepools.kafka.strimzi.io; do sleep 5; done

echo "⏳ Waiting for operator pod to be ready..."
sleep 15
until [ "$(kubectl get pods -n kafka -l name=strimzi-cluster-operator -o jsonpath='{.items[0].status.phase}' 2>/dev/null)" = "Running" ]; do 
  echo -n "."
  sleep 5
done
echo " Operator is Running."

echo "🏗️ [Lab Provisioner] Deploying KRaft Kafka Cluster 'phenix-lab'..."

cat <<EOF | kubectl apply -f - -n kafka
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaNodePool
metadata:
  name: controller
  labels:
    strimzi.io/cluster: phenix-lab
spec:
  replicas: 1
  roles:
    - controller
  storage:
    type: ephemeral
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaNodePool
metadata:
  name: broker
  labels:
    strimzi.io/cluster: phenix-lab
spec:
  replicas: 1
  roles:
    - broker
  storage:
    type: ephemeral
---
apiVersion: kafka.strimzi.io/v1beta2
kind: Kafka
metadata:
  name: phenix-lab
  annotations:
    strimzi.io/node-pools: "enabled"
    strimzi.io/kraft: "enabled"
spec:
  kafka:
    version: 3.8.0
    listeners:
      - name: plain
        port: 9092
        type: internal
        tls: false
      - name: external
        port: 9094
        type: nodeport
        tls: false
        configuration:
          bootstrap:
            nodePort: 30092
    config:
      offsets.topic.replication.factor: 1
      transaction.state.log.replication.factor: 1
      transaction.state.log.min.isr: 1
      default.replication.factor: 1
      min.insync.replicas: 1
      inter.broker.protocol.version: "3.8"
    storage:
      type: ephemeral
  entityOperator:
    topicOperator: {}
    userOperator: {}
EOF

echo "📊 Installing Prometheus (Minimal Setup + CRDs)..."
kubectl create namespace monitoring || true

# Install ONLY the Prometheus Operator CRDs so 'prometheusrule' resource type exists
curl -ksSL https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/main/example/prometheus-operator-crd/monitoring.coreos.com_prometheusrules.yaml -o /tmp/prom-rules.yaml
kubectl apply -f /tmp/prom-rules.yaml || true
curl -ksSL https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/main/example/prometheus-operator-crd/monitoring.coreos.com_servicemonitors.yaml -o /tmp/prom-svc.yaml
kubectl apply -f /tmp/prom-svc.yaml || true
curl -ksSL https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/main/example/prometheus-operator-crd/monitoring.coreos.com_podmonitors.yaml -o /tmp/prom-pod.yaml
kubectl apply -f /tmp/prom-pod.yaml || true

cat <<EOF | kubectl apply -f - -n monitoring
apiVersion: v1
kind: ServiceAccount
metadata:
  name: prometheus
  namespace: monitoring
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: prometheus
rules:
- apiGroups: [""]
  resources: ["nodes", "nodes/proxy", "services", "endpoints", "pods"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: prometheus
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: prometheus
subjects:
- kind: ServiceAccount
  name: prometheus
  namespace: monitoring
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
  namespace: monitoring
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
    scrape_configs:
      - job_name: 'kubernetes-nodes'
        kubernetes_sd_configs:
          - role: node
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus
  namespace: monitoring
spec:
  replicas: 1
  selector:
    matchLabels:
      app: prometheus
  template:
    metadata:
      labels:
        app: prometheus
    spec:
      serviceAccountName: prometheus
      containers:
      - name: prometheus
        image: prom/prometheus:latest
        args:
          - "--config.file=/etc/prometheus/prometheus.yml"
          - "--storage.tsdb.path=/prometheus/"
        ports:
        - containerPort: 9090
        volumeMounts:
        - name: config-volume
          mountPath: /etc/prometheus/
        - name: storage-volume
          mountPath: /prometheus/
      volumes:
      - name: config-volume
        configMap:
          name: prometheus-config
      - name: storage-volume
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: prom-prometheus-server
  namespace: monitoring
spec:
  type: NodePort
  selector:
    app: prometheus
  ports:
    - port: 80
      targetPort: 9090
      nodePort: 30090
EOF

echo "⏳ Waiting for Kafka Readiness..."
until [ "$(kubectl get kafka phenix-lab -n kafka -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)" = "True" ]; do
  echo -n "."
  sleep 10
done
echo " Kafka is Ready!"

echo "✅ [Lab Provisioner] Phenix Lab is ready!"
tail -f /dev/null
