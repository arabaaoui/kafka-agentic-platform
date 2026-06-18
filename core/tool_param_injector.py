"""ToolParamInjectorADKPlugin — auto-inject prom_url / proxy_url / kubeconfig.

Runs as an ADK BasePlugin hook (before_tool_callback) and injects missing
technical parameters from the mission's env config into every tool call.

Injection rules:
  - prom_url  : injected if the tool declares it and caller omitted it
  - proxy_url : injected (with credentials encoded in URL) under same conditions
  - kubeconfig: injected; raises ValueError for non-LAB env without a configured path
"""

from __future__ import annotations

import inspect
import logging
import os
from typing import Any

log = logging.getLogger(__name__)


from google.adk.plugins import BasePlugin
from google.adk.tools import BaseTool
from google.adk.tools.tool_context import ToolContext

from .plugin_base import get_mission_context_from_state


class ToolParamInjectorADKPlugin(BasePlugin):
    """ADK native — before_tool_callback injects missing technical params."""

    def __init__(self, tenant_config: Any | None = None) -> None:
        super().__init__(name="tool_param_injector")
        self._tenant_config = tenant_config

    async def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
    ) -> None:
        from .tenant import TenantRegistry

        mission_ctx = get_mission_context_from_state(tool_context.state)
        if not mission_ctx:
            log.debug("ToolParamInjectorADKPlugin: no mission context in state, skipping injection")
            return

        try:
            tenant_cfg = self._tenant_config or TenantRegistry.get(mission_ctx.tenant)
            env_cfg = tenant_cfg.envs.get(mission_ctx.env.lower())
            if env_cfg:
                declared_params: set[str] = set()
                try:
                    if callable(tool):
                        sig = inspect.signature(tool)
                        declared_params = set(sig.parameters.keys())
                    elif hasattr(tool, "func") and callable(tool.func):
                        sig = inspect.signature(tool.func)
                        declared_params = set(sig.parameters.keys())
                    else:
                        schema = getattr(tool, "args_schema", None) or {}
                        if hasattr(schema, "model_fields"):
                            declared_params = set(schema.model_fields.keys())
                        elif isinstance(schema, dict):
                            declared_params = set(schema.get("properties", {}).keys())
                except Exception:
                    declared_params = {"prom_url", "proxy_url", "kubeconfig"}

                if not declared_params:
                    declared_params = {"prom_url", "proxy_url", "kubeconfig"}

                if "prom_url" in declared_params and not tool_args.get("prom_url"):
                    if env_cfg.prom_url:
                        tool_args["prom_url"] = env_cfg.prom_url

                if "proxy_url" in declared_params and not tool_args.get("proxy_url"):
                    proxy_base = getattr(env_cfg, "proxy_url", None)
                    if proxy_base:
                        user = getattr(env_cfg, "proxy_user", None)
                        password = getattr(env_cfg, "proxy_pass", None)
                        if user and password and "://" in proxy_base and "@" not in proxy_base:
                            scheme, host = proxy_base.split("://", 1)
                            tool_args["proxy_url"] = f"{scheme}://{user}:{password}@{host}"
                        else:
                            tool_args["proxy_url"] = proxy_base

                if "kubeconfig" in declared_params and not tool_args.get("kubeconfig"):
                    if env_cfg.kubeconfig:
                        tool_args["kubeconfig"] = env_cfg.kubeconfig
                        if env_cfg.kube_context:
                            os.environ["KUBECONTEXT"] = env_cfg.kube_context
                    elif mission_ctx.env.lower() != "lab":
                        raise ValueError(
                            f"Environment '{mission_ctx.env}' has no valid kubeconfig configured."
                        )
        except ValueError:
            raise
        except Exception as exc:
            log.debug("ToolParamInjectorADKPlugin: injection skipped — %s", exc)
