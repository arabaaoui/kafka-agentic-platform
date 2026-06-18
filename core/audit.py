"""AuditPlugin — appends every tool call to a JSONL audit log.

Constitution V: zero secrets in audit.  All values matching REDACT_PATTERNS
are replaced with ``"[REDACTED]"`` before writing.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .mission import MissionContext

log = logging.getLogger(__name__)

# Keys whose values must be redacted regardless of nesting depth.
REDACT_PATTERNS = re.compile(
    r"password|secret|token|api_key|kubeconfig|authorization",
    re.IGNORECASE,
)

_MAX_VALUE_LEN = 512  # truncate large result strings to keep audit files reasonable


def _redact(obj: Any) -> Any:
    """Recursively redact sensitive keys from a nested dict/list structure."""
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if REDACT_PATTERNS.search(k) else _redact(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(item) for item in obj]
    if isinstance(obj, str) and len(obj) > _MAX_VALUE_LEN:
        return obj[:_MAX_VALUE_LEN] + "…[truncated]"
    return obj


from google.adk.plugins import BasePlugin
from google.adk.tools import BaseTool
from google.adk.tools.tool_context import ToolContext

from .plugin_base import get_mission_context_from_state


class AuditADKPlugin(BasePlugin):
    """ADK native audit plugin — writes JSONL for every tool call."""

    def __init__(self, *, log_path: str | Path = "audit.jsonl") -> None:
        super().__init__(name="audit")
        self._path = Path(log_path)

    def _append(self, entry: dict[str, Any]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(_redact(entry), ensure_ascii=False) + "\n")
        except OSError as exc:
            log.error("AuditADKPlugin: failed to write: %s", exc)

    async def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
    ) -> None:
        mission_ctx = get_mission_context_from_state(tool_context.state)
        self._append(
            {
                "event": "tool_call",
                "mission_id": mission_ctx.mission_id if mission_ctx else "unknown",
                "env": mission_ctx.env if mission_ctx else "unknown",
                "tool": tool.name,
                "params": tool_args,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def after_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        result: dict,
    ) -> None:
        mission_ctx = get_mission_context_from_state(tool_context.state)
        self._append(
            {
                "event": "tool_result",
                "mission_id": mission_ctx.mission_id if mission_ctx else "unknown",
                "env": mission_ctx.env if mission_ctx else "unknown",
                "tool": tool.name,
                "result_type": type(result).__name__,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )
