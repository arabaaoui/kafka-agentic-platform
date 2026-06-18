"""Unit tests for core/mission_isolation.py (spec 003 T015-T021)."""

import time

import pytest

from core.mission_isolation import (
    _check_access,
    _resolve_target_env,
)
from core.tenant import EnvConfig, TenantConfig


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def tenant_cfg() -> TenantConfig:
    return TenantConfig(
        tenant="testco",
        envs={
            "preprod": EnvConfig(
                clusters=["kafkahub-preprod"],
                kubeconfig="/kube/preprod",
                prom_url="https://prom.preprod.example.com",
                vm_url="https://vm.preprod.example.com",
            ),
            "prod": EnvConfig(
                clusters=["kafkahub-prod"],
                kubeconfig="/kube/prod",
                prom_url="https://prom.prod.example.com",
                vm_url="https://vm.prod.example.com",
            ),
        },
    )


# ── _resolve_target_env ───────────────────────────────────────────────────────


def test_resolve_by_prom_url(tenant_cfg):
    env = _resolve_target_env(
        "prom_query",
        {"prom_url": "https://prom.prod.example.com/api/v1/query"},
        tenant_cfg,
    )
    assert env == "prod"


def test_resolve_by_vm_url(tenant_cfg):
    env = _resolve_target_env(
        "prom_query",
        {"prom_url": "https://vm.preprod.example.com/api/v1"},
        tenant_cfg,
    )
    assert env == "preprod"


def test_resolve_by_kubeconfig(tenant_cfg):
    env = _resolve_target_env(
        "cluster_health",
        {"kubeconfig": "/kube/prod"},
        tenant_cfg,
    )
    assert env == "prod"


def test_resolve_unknown_url_returns_none(tenant_cfg):
    env = _resolve_target_env(
        "prom_query",
        {"prom_url": "https://unknown.example.com/query"},
        tenant_cfg,
    )
    assert env is None


def test_resolve_no_url_params_returns_none(tenant_cfg):
    env = _resolve_target_env("validate_slug", {"value": "pvc-saturation"}, tenant_cfg)
    assert env is None


# ── _check_access ─────────────────────────────────────────────────────────────


def test_same_env_allowed(tenant_cfg):
    allowed = _check_access(
        {"prom_url": "https://prom.preprod.example.com/api/v1/query"},
        tenant_cfg,
        "preprod",
    )
    assert allowed


def test_cross_env_blocked(tenant_cfg):
    allowed = _check_access(
        {"prom_url": "https://prom.prod.example.com/api/v1/query"},
        tenant_cfg,
        "preprod",
    )
    assert not allowed


def test_unknown_url_not_blocked(tenant_cfg):
    allowed = _check_access(
        {"prom_url": "https://totally-unknown.example.com/query"},
        tenant_cfg,
        "preprod",
    )
    assert allowed  # unknown URL → not a known env → allow


def test_cross_env_bidirectional(tenant_cfg):
    allowed = _check_access(
        {"prom_url": "https://prom.preprod.example.com/query"},
        tenant_cfg,
        "prod",
    )
    assert not allowed


# ── Performance guard (spec 003 SC-006: <50ms per check) ─────────────────────


def test_isolation_check_under_50ms(tenant_cfg):
    start = time.perf_counter()
    for _ in range(100):
        _check_access(
            {"prom_url": "https://prom.preprod.example.com/query"},
            tenant_cfg,
            "preprod",
        )
    elapsed_ms = (time.perf_counter() - start) * 1000
    avg_ms = elapsed_ms / 100
    assert avg_ms < 50, f"avg isolation check took {avg_ms:.1f}ms (limit 50ms)"
