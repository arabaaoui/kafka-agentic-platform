"""Mission isolation plugin — blocks cross-env tool calls (constitution II).

Every tool call is inspected: if any parameter resolves to an endpoint or
kubeconfig belonging to a *different* env than the active mission, the call
is hard-blocked and logged to audit.jsonl.  Resolution uses TenantConfig so
the list of known envs is never hardcoded here (constitution VII).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .mission import MissionContext
    from .tenant import TenantConfig

log = logging.getLogger(__name__)

# Parameters that may carry endpoint URLs or kubeconfig paths.
_URL_PARAMS = ("prom_url", "vm_url", "url", "endpoint", "base_url")
_KUBECONFIG_PARAMS = ("kubeconfig",)

# Tools that are always allowed regardless of env (pure computation, no remote I/O).
_ENV_AGNOSTIC_TOOLS = frozenset(
    {
        "validate_slug",
        "build_mission_id",
        "format_audit",
        "echo",
        "noop",
    }
)

_AUDIT_FILE = Path("audit.jsonl")


class CrossEnvAccessBlocked(Exception):
    """Raised when a tool call targets an env that differs from the mission env."""

    def __init__(
        self,
        *,
        mission_id: str,
        tool_name: str,
        tool_params: dict[str, Any],
        mission_env: str,
        target_env: str,
    ) -> None:
        self.mission_id = mission_id
        self.tool_name = tool_name
        self.tool_params = tool_params
        self.mission_env = mission_env
        self.target_env = target_env
        super().__init__(
            f"CrossEnvAccessBlocked: tool '{tool_name}' targets env '{target_env}' "
            f"but mission '{mission_id}' is locked to env '{mission_env}'"
        )


def _resolve_target_env(
    tool_name: str,
    tool_params: dict[str, Any],
    tenant_config: "TenantConfig",
) -> str | None:
    """Return the env name inferred from tool parameters, or None if unresolvable."""
    flat_urls = [
        str(v)
        for k, v in tool_params.items()
        if k in _URL_PARAMS and isinstance(v, str) and v.startswith("http")
    ]
    flat_kubeconfigs = [
        str(v)
        for k, v in tool_params.items()
        if k in _KUBECONFIG_PARAMS and isinstance(v, str) and v
    ]

    for env_name, env_cfg in tenant_config.envs.items():
        for url in flat_urls:
            if any(url.startswith(ep) for ep in env_cfg.endpoints if ep):
                return env_name
        for kc in flat_kubeconfigs:
            if env_cfg.kubeconfig and kc == env_cfg.kubeconfig:
                return env_name

    return None


def _check_access(
    tool_params: dict[str, Any],
    tenant_config: "TenantConfig",
    mission_env: str,
) -> bool:
    """Return True if the tool call is authorized for the given mission env.
    
    A call is authorized if all targeted endpoints/kubeconfigs either:
    1. Belong to the mission's environment.
    2. Belong to NO known environment (e.g. external global APIs).
    
    In a Lab environment where multiple logical envs share the same physical
    endpoint, this logic ensures that targeting the shared endpoint is allowed
    for any of those logical envs.
    """
    flat_urls = [
        str(v)
        for k, v in tool_params.items()
        if k in _URL_PARAMS and isinstance(v, str) and v.startswith("http")
    ]
    flat_kubeconfigs = [
        str(v)
        for k, v in tool_params.items()
        if k in _KUBECONFIG_PARAMS and isinstance(v, str) and v
    ]

    mission_env_cfg = tenant_config.envs.get(mission_env.lower())
    if not mission_env_cfg:
        return True # Logical env not found (e.g. bootstrap), allow

    # Check URLs
    for url in flat_urls:
        # Is this URL one of the mission env's authorized endpoints?
        if any(url.startswith(ep) for ep in mission_env_cfg.endpoints if ep):
            continue # Authorized for this mission env
            
        # URL is NOT in mission env. Is it in ANY OTHER env?
        for other_env, other_cfg in tenant_config.envs.items():
            if other_env.lower() == mission_env.lower():
                continue
            if any(url.startswith(ep) for ep in other_cfg.endpoints if ep):
                # It belongs to a DIFFERENT env with a DIFFERENT endpoint. Block.
                return False

    # Check Kubeconfigs
    for kc in flat_kubeconfigs:
        if mission_env_cfg.kubeconfig and kc == mission_env_cfg.kubeconfig:
            continue
            
        for other_env, other_cfg in tenant_config.envs.items():
            if other_env.lower() == mission_env.lower():
                continue
            if other_cfg.kubeconfig and kc == other_cfg.kubeconfig:
                return False

    return True


def _append_audit(entry: dict[str, Any], audit_path: Path) -> None:
    """Append a JSON line to audit.jsonl (non-fatal if file system error)."""
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.error("MissionIsolationPlugin: failed to write audit entry: %s", exc)


from google.adk.plugins import BasePlugin
from google.adk.tools import BaseTool
from google.adk.tools.tool_context import ToolContext

from .plugin_base import get_mission_context_from_state


class MissionIsolationADKPlugin(BasePlugin):
    """ADK native mission isolation — blocks cross-env tool calls."""

    def __init__(
        self,
        *,
        tenant_config: Any,
        audit_path: "Path | str" = _AUDIT_FILE,
    ) -> None:
        super().__init__(name="mission_isolation")
        self._tenant_config = tenant_config
        self._audit_path = Path(audit_path)

    async def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
    ) -> None:
        if tool.name in _ENV_AGNOSTIC_TOOLS:
            return

        mission_ctx = get_mission_context_from_state(tool_context.state)
        if not mission_ctx:
            return

        if not _check_access(tool_args, self._tenant_config, mission_ctx.env):
            target_env = _resolve_target_env(tool.name, tool_args, self._tenant_config) or "unknown"

            entry: dict[str, Any] = {
                "event": "cross_env_blocked",
                "mission_id": mission_ctx.mission_id,
                "tool": tool.name,
                "target_env": target_env,
                "mission_env": mission_ctx.env,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            _append_audit(entry, self._audit_path)

            raise CrossEnvAccessBlocked(
                mission_id=mission_ctx.mission_id,
                tool_name=tool.name,
                tool_params=tool_args,
                mission_env=mission_ctx.env,
                target_env=target_env,
            )
