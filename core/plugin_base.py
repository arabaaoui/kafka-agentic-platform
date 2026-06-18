"""Plugin base — helpers shared by all ADK BasePlugin implementations.

The platform uses google.adk.plugins.BasePlugin natively.
MissionContext is passed through ADK session.state["_mission_context"].
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .mission import MissionContext

# Key used to store MissionContext in ADK session state.
_MISSION_CTX_KEY = "_mission_context"


def get_mission_context_from_state(state: Any) -> Optional["MissionContext"]:
    """Extract MissionContext from ADK session state (or dict-like state)."""
    try:
        return state[_MISSION_CTX_KEY]
    except (KeyError, TypeError):
        return None
