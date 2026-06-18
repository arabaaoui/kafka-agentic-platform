"""Tenant configuration loader — reads tenants/{tenant}.yaml at runtime.

All Carrefour-specific values live in tenants/carrefour.yaml.
No tenant value may appear in this module (constitution VII).
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class EnvConfig(BaseModel):
    """Per-environment configuration block inside a tenant YAML."""

    display_name: str = ""
    badge_color: str = "gray"
    clusters: list[str]
    kubeconfig: str
    kube_context: str = ""
    kubeconfig_content: str = ""
    gcp_project: str = ""
    kafka_namespace: str = ""
    prom_url: str
    alertmanager_url: str = ""
    proxy_url: str = ""
    proxy_user: str = ""
    proxy_pass: str = ""
    vm_url: str = ""
    vault_path: str = ""
    care_env: str = ""
    target_gsa_email: str = ""

    @field_validator("kubeconfig", mode="before")
    @classmethod
    def _expand_env_vars(cls, v: str) -> str:
        return os.path.expandvars(v)

    @field_validator("prom_url", "vm_url", "alertmanager_url", mode="before")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/") if v else v

    @property
    def endpoints(self) -> list[str]:
        """All URL endpoints for this env — used by MissionIsolationPlugin for matching."""
        return [u for u in (self.prom_url, self.vm_url, self.alertmanager_url) if u]


class BootstrapFilter(BaseModel):
    scope: str
    name: str
    enabled: bool = True
    criteria: dict[str, Any]


class TenantConfig(BaseModel):
    """Full tenant configuration loaded from tenants/{tenant}.yaml."""

    tenant: str
    display_name: str = ""
    autonomy_level: str = "L2"
    jira_projects: list[str] = Field(default_factory=list)
    bootstrap_filter: BootstrapFilter | None = None
    envs: dict[str, EnvConfig]

    @model_validator(mode="after")
    def _require_at_least_one_env(self) -> "TenantConfig":
        if not self.envs:
            raise ValueError(f"Tenant '{self.tenant}' must define at least one env")
        return self

    def env_for_endpoint(self, url: str) -> str | None:
        """Return the env name that owns the given URL prefix, or None."""
        for env_name, env_cfg in self.envs.items():
            if any(url.startswith(ep) for ep in env_cfg.endpoints if ep):
                return env_name
        return None

    def env_for_cluster(self, cluster: str) -> str | None:
        """Return the env name that contains the given cluster, or None."""
        for env_name, env_cfg in self.envs.items():
            if cluster in env_cfg.clusters:
                return env_name
        return None


def load_tenant(path: str | Path) -> TenantConfig:
    """Load and validate a single tenant YAML file.

    Args:
        path: Path to a tenants/{slug}.yaml file.

    Returns:
        Validated TenantConfig.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValidationError: If the YAML fails Pydantic validation.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Tenant config not found: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return TenantConfig(**raw)


def load_tenants_dir(tenants_dir: str | Path) -> dict[str, TenantConfig]:
    """Load all *.yaml files in a directory as tenant configs.

    Returns a dict keyed by tenant slug (filename stem).
    Files that fail validation are skipped with a warning.
    """
    import warnings

    base = Path(tenants_dir)
    if not base.exists():
        return {}
    configs: dict[str, TenantConfig] = {}
    for f in sorted(base.glob("*.yaml")):
        try:
            cfg = load_tenant(f)
            configs[cfg.tenant] = cfg
        except Exception as exc:
            warnings.warn(f"Skipping tenant config {f.name}: {exc}", stacklevel=2)
    return configs


class TenantRegistry:
    """Thread-safe singleton holding the active tenant configs.

    Supports hot-reload via reload() without server restart (spec 003 FR-005).
    """

    _lock = threading.Lock()
    _configs: dict[str, TenantConfig] = {}
    _tenants_dir: Path | None = None

    @classmethod
    def init(cls, tenants_dir: str | Path) -> None:
        cls._tenants_dir = Path(tenants_dir)
        cls.reload()

    @classmethod
    def reload(cls) -> dict[str, TenantConfig]:
        """Re-read all tenant YAMLs. Raises ValueError if any file is invalid.

        On validation error, the current configs remain active (no partial reload).
        """
        if cls._tenants_dir is None:
            raise RuntimeError("TenantRegistry.init() must be called before reload()")
        new_configs = load_tenants_dir(cls._tenants_dir)
        if not new_configs:
            raise ValueError(f"No valid tenant configs found in {cls._tenants_dir}")
        with cls._lock:
            cls._configs = new_configs
        return new_configs

    @classmethod
    def get(cls, tenant: str) -> TenantConfig:
        with cls._lock:
            # Try exact match first, then lowercase
            cfg = cls._configs.get(tenant) or cls._configs.get(tenant.lower())
        if cfg is None:
            raise KeyError(f"Tenant not found: {tenant!r}. Known tenants: {list(cls._configs)}")
        return cfg

    @classmethod
    def all(cls) -> dict[str, TenantConfig]:
        with cls._lock:
            return dict(cls._configs)

    @classmethod
    def add_env_override(cls, tenant: str, slug: str, config: EnvConfig) -> None:
        """Manually inject or update an environment config in memory."""
        with cls._lock:
            t_cfg = cls._configs.get(tenant)
            if not t_cfg:
                raise KeyError(f"Tenant '{tenant}' not found")
            t_cfg.envs[slug] = config

    @classmethod
    def remove_env_override(cls, tenant: str, slug: str) -> None:
        """Remove an environment config from memory."""
        with cls._lock:
            t_cfg = cls._configs.get(tenant)
            if t_cfg and slug in t_cfg.envs:
                del t_cfg.envs[slug]
