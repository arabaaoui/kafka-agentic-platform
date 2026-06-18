#!/bin/bash
set -e

echo "Updating CA certificates..."
update-ca-certificates
export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
export GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=/etc/ssl/certs/ca-certificates.crt

echo "Running database migrations..."
uv run alembic upgrade head

# ── GKE AUTH FIX (Local Dev) ──────────────────────────────────────────────
# Copy mounted gcloud config to a local writable directory with correct permissions
mkdir -p /root/.config/gcloud
if [ -d /root/.config/gcloud-host ]; then
    echo "Syncing gcloud config from host..."
    cp -a /root/.config/gcloud-host/. /root/.config/gcloud/
    chmod -R 700 /root/.config/gcloud
fi
export CLOUDSDK_CONFIG=/root/.config/gcloud
# ──────────────────────────────────────────────────────────────────────────

if [ $# -gt 0 ]; then
    echo "Executing command: $@"
    exec "$@"
fi

echo "Starting application..."
exec uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --loop asyncio
