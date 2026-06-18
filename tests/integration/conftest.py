"""Integration test fixtures — FastAPI test client + mocked external services."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.tenant import TenantRegistry


@pytest.fixture()
def tenants_dir(tmp_path) -> Path:
    content = textwrap.dedent("""\
        tenant: carrefour
        envs:
          preprod:
            clusters: [kafka-preprod]
            kubeconfig: /kube/preprod
            prom_url: https://prom.preprod.example.com
            vm_url: https://vm.preprod.example.com
    """)
    (tmp_path / "carrefour.yaml").write_text(content)
    return tmp_path


@pytest.fixture()
def app(tenants_dir, monkeypatch):
    monkeypatch.setenv("TENANTS_DIR", str(tenants_dir))
    # Avoid real DB + poller startup in tests
    import api.main as main_mod

    from contextlib import asynccontextmanager
    from typing import AsyncGenerator

    @asynccontextmanager
    async def _test_lifespan(app):
        TenantRegistry.init(str(tenants_dir))
        yield

    monkeypatch.setattr(main_mod, "lifespan", _test_lifespan)
    from api.main import create_app
    return create_app()


@pytest.fixture()
def client(app) -> TestClient:
    with TestClient(app) as c:
        yield c
