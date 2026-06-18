.PHONY: install dev test lint eval migrate lab-up lab-down

# ── Dependencies ──────────────────────────────────────────────────────────────
install:
	uv sync --all-extras

# ── Dev server ────────────────────────────────────────────────────────────────
dev:
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

dev-web:
	cd web && npm run dev

# ── Database ──────────────────────────────────────────────────────────────────
migrate:
	alembic upgrade head

migrate-down:
	alembic downgrade -1

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	uv run pytest tests/unit tests/integration -v --tb=short

test-unit:
	uv run pytest tests/unit -v --tb=short

test-e2e:
	uv run pytest tests/e2e -v --tb=short -s

test-all:
	uv run pytest tests/ -v --tb=short

# ── Eval suite (Promptfoo — CI gate ≥80%) ─────────────────────────────────────
eval:
	cd evals && promptfoo eval --config promptfoo.yaml --output results.json
	@python3 -c "import json,sys; r=json.load(open('evals/results.json')); p=r.get('stats',{}).get('passRate',0); print(f'Pass rate: {p:.1%}'); sys.exit(0 if p>=0.8 else 1)"

# ── Lint ──────────────────────────────────────────────────────────────────────
lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

# ── Orchestration (Lab vs App) ────────────────────────────────────────────────
COMPOSE = docker compose -f deploy/docker-compose.yml

# Full stack (Default)
lab-up:
	$(COMPOSE) --profile lab --profile app up -d
	@echo "⏳ Checking if Lab needs provisionning (this may take a few seconds)..."
	@docker logs platform-backend 2>&1 | grep -q "ready" || echo "Note: Lab might still be starting in background."
	@echo "✅ Services started. Use 'make lab-wait' if you need to be sure Kafka is ready."

# Explicit wait only when needed
lab-wait:
	@echo "Waiting for lab provisioner…"
	@docker logs -f phenix-lab-provisioner 2>&1 | grep -m1 "Phenix Lab is ready"
	@echo "✅ [Lab Provisioner] Phenix Lab is ready!"

lab-down:
	$(COMPOSE) --profile lab --profile app down

# Application only (Frontend + Backend + Shared Infra)
# Rebuilds the app without restarting the slow K3s lab
app-up:
	$(COMPOSE) --profile app up -d --build
	@echo "✅ Application (Frontend/Backend) is up!"

app-down:
	$(COMPOSE) --profile app stop

app-restart:
	$(COMPOSE) --profile app restart

# Autonomous Lab only (K3s + Kafka UI + Provisioner)
# Run once, keep running while working on app
infra-lab-up:
	$(COMPOSE) --profile lab up -d
	@echo "Waiting for lab provisioner…"
	@docker logs -f phenix-lab-provisioner 2>&1 | grep -m1 "Phenix Lab is ready"
	@echo "✅ [Lab Provisioner] Phenix Lab is ready!"

infra-lab-down:
	$(COMPOSE) --profile lab down

lab-status:
	docker exec phenix-lab-provisioner kubectl get pods -A 2>/dev/null || echo "Lab not running"

lab-fill:
	./deploy/lab/kafka-filler.sh

# ── Secrets audit ─────────────────────────────────────────────────────────────
audit-secrets:
	@if [ -f audits/*/audit.jsonl ]; then \
	  grep -riE 'password|secret|token|api_key|kubeconfig|Authorization' audits/*/audit.jsonl && echo "FAIL: secrets found" && exit 1 || echo "OK: no secrets found"; \
	fi
