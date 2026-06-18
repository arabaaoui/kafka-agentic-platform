"""ADK-native plugin system for kafka-agentic-platform.

All tool calls go through ADK BasePlugin hooks registered on the Runner.
Plugin order (canonical):
  GuardrailsPlugin → ResiliencePlugin → ToolParamInjectorPlugin → AuditPlugin →
  ActivityPlugin → MissionIsolationPlugin → AutonomyPlugin → ErrorHandlerPlugin →
  AutoTracingPlugin
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from google.adk.plugins import BasePlugin
from google.adk.tools import BaseTool
from google.adk.tools.tool_context import ToolContext

from .plugin_base import _MISSION_CTX_KEY, get_mission_context_from_state

if TYPE_CHECKING:
    from .mission import MissionContext

log = logging.getLogger(__name__)

_AUDIT_BASE = Path(os.getenv("AUDIT_DIR", "/app/audits"))


# ── Concrete plugin imports ───────────────────────────────────────────────────

from .audit import AuditADKPlugin  # noqa: E402
from .autonomy import AutonomyADKPlugin  # noqa: E402
from .mission_isolation import MissionIsolationADKPlugin  # noqa: E402
from .tool_param_injector import ToolParamInjectorADKPlugin  # noqa: E402
from .langfuse_plugin import LangfuseADKPlugin  # noqa: E402


# ── Internal ADK plugin stubs ─────────────────────────────────────────────────


class _GuardrailsADKPlugin(BasePlugin):
    def __init__(self) -> None:
        super().__init__(name="guardrails")

    async def before_tool_callback(
        self, *, tool: BaseTool, tool_args: dict, tool_context: ToolContext
    ) -> None:
        tool_name = tool.name
        if not tool_name or not isinstance(tool_name, str):
            raise ValueError(f"GuardrailsPlugin: invalid tool name: {tool_name!r}")
        if not isinstance(tool_args, dict):
            raise ValueError(f"GuardrailsPlugin: tool_args must be a dict, got {type(tool_args)}")


class _ResilienceADKPlugin(BasePlugin):
    def __init__(self) -> None:
        super().__init__(name="resilience")


class _ActivityADKPlugin(BasePlugin):
    def __init__(self) -> None:
        super().__init__(name="activity")


class _ErrorHandlerADKPlugin(BasePlugin):
    def __init__(self) -> None:
        super().__init__(name="error_handler")


# ── ADK plugin list factory ───────────────────────────────────────────────────


def build_plugin_list(
    *,
    mission_context: "MissionContext",
    tenant_config: Any,
    autonomy_level: str = "L2",
    audit_path: str | Path | None = None,
) -> list[BasePlugin]:
    """Build the ordered list of ADK BasePlugin instances for the Runner.

    Canonical order:
      GuardrailsPlugin → ResiliencePlugin → ToolParamInjectorPlugin → AuditPlugin →
      ActivityPlugin → MissionIsolationPlugin → AutonomyPlugin → ErrorHandlerPlugin →
      AutoTracingPlugin
    """
    from google.adk.plugins.auto_tracing_plugin import AutoTracingPlugin

    audit_base = Path(os.getenv("AUDIT_DIR", "/app/audits"))
    if audit_path is None and mission_context is not None:
        audit_path = audit_base / mission_context.mission_id / "audit.jsonl"
    elif audit_path is None:
        audit_path = audit_base / "system_audit.jsonl"

    return [
        _GuardrailsADKPlugin(),
        _ResilienceADKPlugin(),
        ToolParamInjectorADKPlugin(tenant_config=tenant_config),
        AuditADKPlugin(log_path=audit_path),
        _ActivityADKPlugin(),
        MissionIsolationADKPlugin(tenant_config=tenant_config),
        AutonomyADKPlugin(level=autonomy_level),
        _ErrorHandlerADKPlugin(),
        AutoTracingPlugin(),
        LangfuseADKPlugin(),
    ]
