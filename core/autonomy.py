"""AutonomyPlugin — enforces L2 read-only constraint (constitution I).

L2 blocks any tool that could mutate state: topic creation/deletion, partition
reassignment, SCRAM user management, kubectl apply/delete, etc.  The blocked
list is declared explicitly here; new mutating tools must be added to stay safe.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .mission import MissionContext

log = logging.getLogger(__name__)

# Tools blocked at L2 (read-only).  L3+ can override on opt-in basis (post-v0).
_L2_BLOCKED_TOOLS: frozenset[str] = frozenset(
    {
        # Kafka topic management
        "topic_create",
        "topic_delete",
        "topic_alter_config",
        "topic_set_retention",
        # Partition / reassignment
        "kafka_reassign",
        "kafka_preferred_replica_election",
        "partition_move",
        # Consumer groups
        "consumer_group_reset_offset",
        "consumer_group_delete",
        # SCRAM / security
        "scram_user_create",
        "scram_user_delete",
        "scram_user_update_password",
        "acl_create",
        "acl_delete",
        # Kubernetes
        "kubectl_apply",
        "kubectl_delete",
        "kubectl_scale",
        "kubectl_rollout_restart",
        "kubectl_patch",
        "kubectl_edit",
        # Strimzi custom resources
        "kafka_cr_patch",
        "strimzi_rolling_update",
        # Jira / external write
        "jira_add_comment",
        "jira_transition_issue",
        "jira_create_issue",
        # Care / SMA-X
        "care_update",
        "care_close",
    }
)


class AutonomyViolation(Exception):
    """Raised when a blocked tool is called at the current autonomy level."""

    def __init__(self, *, tool_name: str, level: str, mission_id: str) -> None:
        self.tool_name = tool_name
        self.level = level
        self.mission_id = mission_id
        super().__init__(
            f"AutonomyViolation: tool '{tool_name}' is blocked at autonomy level "
            f"'{level}' for mission '{mission_id}'"
        )


from google.adk.plugins import BasePlugin
from google.adk.tools import BaseTool
from google.adk.tools.tool_context import ToolContext

from .plugin_base import get_mission_context_from_state


class AutonomyADKPlugin(BasePlugin):
    """ADK native autonomy enforcer — blocks mutating tools at L2."""

    def __init__(self, *, level: str = "L2") -> None:
        super().__init__(name="autonomy")
        self._level = level.upper()

    async def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
    ) -> None:
        mission_ctx = get_mission_context_from_state(tool_context.state)
        effective_level = self._level
        if mission_ctx:
            effective_level = (mission_ctx.autonomy_level or self._level).upper()

        if effective_level == "L2" and tool.name in _L2_BLOCKED_TOOLS:
            mission_id = mission_ctx.mission_id if mission_ctx else "unknown"
            raise AutonomyViolation(
                tool_name=tool.name,
                level=effective_level,
                mission_id=mission_id,
            )
