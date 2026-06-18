"""Unit tests for core/tenant.py (spec 003 T038-T051)."""

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.tenant import (
    EnvConfig,
    TenantConfig,
    TenantRegistry,
    load_tenant,
    load_tenants_dir,
)


# ── EnvConfig ─────────────────────────────────────────────────────────────────


def test_env_config_minimal():
    cfg = EnvConfig(
        clusters=["kafkahub-preprod"],
        kubeconfig="/home/user/.kube/preprod",
        prom_url="https://prom.preprod.example.com",
    )
    assert cfg.prom_url == "https://prom.preprod.example.com"


def test_env_config_strips_trailing_slash():
    cfg = EnvConfig(
        clusters=["c"],
        kubeconfig="/kube",
        prom_url="https://prom.example.com/",
        vm_url="https://vm.example.com//",
    )
    assert not cfg.prom_url.endswith("/")
    assert not cfg.vm_url.endswith("/")


def test_env_config_expands_env_vars(monkeypatch):
    monkeypatch.setenv("HOME", "/home/tester")
    cfg = EnvConfig(
        clusters=["c"],
        kubeconfig="$HOME/.kube/config",
        prom_url="https://prom.example.com",
    )
    assert cfg.kubeconfig == "/home/tester/.kube/config"


def test_env_config_endpoints_no_empty():
    cfg = EnvConfig(
        clusters=["c"],
        kubeconfig="/kube",
        prom_url="https://prom.example.com",
        vm_url="",
    )
    assert cfg.endpoints == ["https://prom.example.com"]


# ── TenantConfig ─────────────────────────────────────────────────────────────


def test_tenant_config_requires_at_least_one_env():
    with pytest.raises(ValidationError):
        TenantConfig(tenant="t", envs={})


def test_tenant_config_env_for_endpoint():
    cfg = TenantConfig(
        tenant="t",
        envs={
            "preprod": EnvConfig(clusters=["c"], kubeconfig="/kube", prom_url="https://prom.preprod.example.com"),
            "prod": EnvConfig(clusters=["d"], kubeconfig="/kube2", prom_url="https://prom.prod.example.com"),
        },
    )
    assert cfg.env_for_endpoint("https://prom.preprod.example.com/api/v1/query") == "preprod"
    assert cfg.env_for_endpoint("https://prom.prod.example.com/api/v1/query") == "prod"
    assert cfg.env_for_endpoint("https://unknown.example.com") is None


def test_tenant_config_env_for_cluster():
    cfg = TenantConfig(
        tenant="t",
        envs={
            "preprod": EnvConfig(clusters=["kafkahub-preprod"], kubeconfig="/kube", prom_url="https://p.example.com"),
            "prod": EnvConfig(clusters=["kafkahub-prod"], kubeconfig="/kube2", prom_url="https://p2.example.com"),
        },
    )
    assert cfg.env_for_cluster("kafkahub-preprod") == "preprod"
    assert cfg.env_for_cluster("kafkahub-prod") == "prod"
    assert cfg.env_for_cluster("unknown-cluster") is None


# ── load_tenant ───────────────────────────────────────────────────────────────


def test_load_tenant_valid(tmp_path):
    yaml_content = textwrap.dedent("""\
        tenant: testco
        envs:
          preprod:
            clusters: [kafkahub-preprod]
            kubeconfig: /kube
            prom_url: https://prom.preprod.example.com
    """)
    f = tmp_path / "testco.yaml"
    f.write_text(yaml_content)
    cfg = load_tenant(f)
    assert cfg.tenant == "testco"
    assert "preprod" in cfg.envs


def test_load_tenant_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_tenant(tmp_path / "nonexistent.yaml")


def test_load_tenant_bad_yaml_rejected(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("tenant: t\nenvs: not_a_dict")
    with pytest.raises(Exception):
        load_tenant(f)


def test_load_tenant_no_envs_rejected(tmp_path):
    f = tmp_path / "nenv.yaml"
    f.write_text("tenant: t\nenvs: {}")
    with pytest.raises(Exception):
        load_tenant(f)


# ── load_tenants_dir ──────────────────────────────────────────────────────────


def test_load_tenants_dir_skips_invalid(tmp_path):
    valid = textwrap.dedent("""\
        tenant: good
        envs:
          preprod:
            clusters: [c]
            kubeconfig: /k
            prom_url: https://p.example.com
    """)
    (tmp_path / "good.yaml").write_text(valid)
    (tmp_path / "bad.yaml").write_text("tenant: bad\nenvs: {}")
    configs = load_tenants_dir(tmp_path)
    assert "good" in configs
    assert "bad" not in configs


def test_load_tenants_dir_empty_dir(tmp_path):
    assert load_tenants_dir(tmp_path) == {}


def test_load_tenants_dir_nonexistent(tmp_path):
    assert load_tenants_dir(tmp_path / "missing") == {}


# ── TenantRegistry ────────────────────────────────────────────────────────────


def _write_valid_yaml(path: Path, tenant: str, prom_url: str) -> None:
    path.write_text(
        textwrap.dedent(f"""\
            tenant: {tenant}
            envs:
              preprod:
                clusters: [c]
                kubeconfig: /kube
                prom_url: {prom_url}
        """)
    )


def test_tenant_registry_init_and_get(tmp_path):
    _write_valid_yaml(tmp_path / "alpha.yaml", "alpha", "https://prom.alpha.example.com")
    TenantRegistry.init(tmp_path)
    cfg = TenantRegistry.get("alpha")
    assert cfg.tenant == "alpha"


def test_tenant_registry_get_unknown_raises(tmp_path):
    _write_valid_yaml(tmp_path / "alpha.yaml", "alpha", "https://prom.alpha.example.com")
    TenantRegistry.init(tmp_path)
    with pytest.raises(KeyError, match="unknown"):
        TenantRegistry.get("unknown")


def test_tenant_registry_reload(tmp_path):
    _write_valid_yaml(tmp_path / "alpha.yaml", "alpha", "https://prom.alpha.example.com")
    TenantRegistry.init(tmp_path)
    # Add another tenant file and reload
    _write_valid_yaml(tmp_path / "beta.yaml", "beta", "https://prom.beta.example.com")
    TenantRegistry.reload()
    assert "beta" in TenantRegistry.all()


def test_tenant_registry_reload_without_init_raises():
    TenantRegistry._tenants_dir = None  # reset
    with pytest.raises(RuntimeError, match="init"):
        TenantRegistry.reload()
