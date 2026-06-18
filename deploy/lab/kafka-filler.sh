#!/bin/bash
# kafka-filler.sh (Background Edition)

NAMESPACE="kafka"
CLUSTER="phenix-lab"
POD_NAME="$CLUSTER-broker-0"
TOPIC="orders"

echo "🧪 Création du topic '$TOPIC'..."
docker exec platform-backend kubectl exec -n $NAMESPACE $POD_NAME -- \
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic $TOPIC --partitions 3 --replication-factor 1 --if-not-exists

echo "📨 Envoi de 1000 messages de test..."
docker exec platform-backend sh -c "seq 1000 | kubectl exec -i -n $NAMESPACE $POD_NAME -- /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic $TOPIC"

echo "📥 Consommation partielle (génération de lag)..."
# On lance le consumer en arrière-plan pour ne pas bloquer le script
docker exec -d platform-backend kubectl exec -n $NAMESPACE $POD_NAME -- \
  /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic $TOPIC --group orders-consumer --max-messages 500

echo "✅ Données injectées en tâche de fond."
