"""LangfuseADKPlugin — ADK-native plugin for Langfuse v2 REST-based tracing."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional, TYPE_CHECKING
from google.adk.plugins import BasePlugin
from google.adk.tools import BaseTool
from google.adk.tools.tool_context import ToolContext
from langfuse import Langfuse

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.agents.callback_context import CallbackContext
    from google.adk.models.llm_request import LlmRequest
    from google.adk.models.llm_response import LlmResponse

log = logging.getLogger(__name__)


class LangfuseADKPlugin(BasePlugin):
    """ADK native plugin for Langfuse v2 REST-based tracing."""

    def __init__(self) -> None:
        super().__init__(name="langfuse_tracing")
        self.langfuse = None
        
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        host = os.getenv("LANGFUSE_HOST", "http://langfuse:3000").rstrip("/")
        
        if public_key and secret_key:
            try:
                self.langfuse = Langfuse(
                    public_key=public_key,
                    secret_key=secret_key,
                    host=host
                )
                log.info("Langfuse v2 REST-based tracing plugin initialized successfully on: %s", host)
            except Exception as exc:
                log.warning("Langfuse REST-based tracing plugin failed to initialize: %s", exc)

        # Thread-safe/session-safe state storage mapped by session ID
        self._traces: dict[str, Any] = {}
        self._models: dict[str, Any] = {}
        self._tool_spans: dict[str, Any] = {}

    async def before_run_callback(
        self, *, invocation_context: InvocationContext
    ) -> None:
        if not self.langfuse:
            return

        session_id = invocation_context.session.id if invocation_context.session else "unknown_session"
        root_agent_name = invocation_context.agent.name if invocation_context.agent else "kafka_agent"
        
        state = invocation_context.session.state if invocation_context.session else {}
        from .plugin_base import _MISSION_CTX_KEY
        mission_ctx = state.get(_MISSION_CTX_KEY)

        try:
            # Start a native Langfuse v2 trace
            trace = self.langfuse.trace(
                name=root_agent_name,
                session_id=mission_ctx.mission_id if mission_ctx else session_id,
                user_id="system",
                metadata={
                    "tenant": mission_ctx.tenant if mission_ctx else "unknown",
                    "env": mission_ctx.env if mission_ctx else "unknown",
                    "cluster": mission_ctx.cluster if mission_ctx else "unknown",
                    "subject": mission_ctx.subject if mission_ctx else "unknown",
                    "jira_ticket": mission_ctx.metadata.get("jira_ticket_id", "N/A") if mission_ctx and mission_ctx.metadata else "N/A",
                }
            )
            self._traces[session_id] = trace
            log.info("Langfuse REST trace started for session %s: %s", session_id, trace.id)
        except Exception as exc:
            log.warning("LangfuseADKPlugin: failed to start trace: %s", exc, exc_info=True)

    async def after_run_callback(
        self, *, invocation_context: InvocationContext
    ) -> None:
        session_id = invocation_context.session.id if invocation_context.session else None
        if not session_id:
            return
            
        trace = self._traces.pop(session_id, None)
        if not trace:
            return

        try:
            # Update and flush v2 trace
            trace.update(
                output="Agent execution finished successfully."
            )
            self.langfuse.flush()
            log.info("Langfuse REST trace finished and flushed for session %s", session_id)
        except Exception as exc:
            log.warning("LangfuseADKPlugin: failed to update trace: %s", exc)

    async def before_model_callback(
        self, *, callback_context: CallbackContext, llm_request: LlmRequest
    ) -> None:
        if not self.langfuse:
            return

        session_id = callback_context.session.id if callback_context.session else None
        if not session_id:
            return
            
        parent_trace = self._traces.get(session_id)
        if not parent_trace:
            return

        try:
            prompt_text = ""
            if hasattr(llm_request, "contents") and llm_request.contents:
                try:
                    prompt_text = str(llm_request.contents)
                except Exception:
                    pass

            inv_ctx = callback_context.get_invocation_context()
            agent_name = inv_ctx.agent.name if inv_ctx and inv_ctx.agent else "agent"

            # Create a v2 Generation
            generation = parent_trace.generation(
                name=f"{agent_name} - Gemini Call",
                model=llm_request.model or "gemini-2.5-flash",
                input=prompt_text,
            )
            self._models[session_id] = generation
        except Exception as exc:
            log.warning("LangfuseADKPlugin: failed to log before model: %s", exc)

    async def after_model_callback(
        self, *, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> None:
        session_id = callback_context.session.id if callback_context.session else None
        if not session_id:
            return
            
        generation = self._models.pop(session_id, None)
        if not generation:
            return

        try:
            output_text = ""
            if hasattr(llm_response, "text") and llm_response.text:
                output_text = llm_response.text
            elif hasattr(llm_response, "content") and llm_response.content:
                output_text = str(llm_response.content)

            input_tokens = 0
            output_tokens = 0
            if hasattr(llm_response, "usage_metadata") and llm_response.usage_metadata:
                try:
                    input_tokens = getattr(llm_response.usage_metadata, "prompt_token_count", 0)
                    output_tokens = getattr(llm_response.usage_metadata, "candidates_token_count", 0)
                except Exception:
                    pass

            # Update v2 Generation
            generation.update(
                output=output_text,
                usage={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                }
            )
        except Exception as exc:
            log.warning("LangfuseADKPlugin: failed to log after model: %s", exc)

    async def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
    ) -> Optional[dict]:
        if not self.langfuse:
            return None

        session_id = tool_context.session.id if tool_context.session else None
        if not session_id:
            return None
            
        parent_trace = self._traces.get(session_id)
        if not parent_trace:
            return None

        try:
            # Create a v2 Span
            span = parent_trace.span(
                name=f"Tool Call: {tool.name}",
                input=tool_args,
            )
            self._tool_spans[session_id] = span
        except Exception as exc:
            log.warning("LangfuseADKPlugin: failed to log before tool: %s", exc)
        return None

    async def after_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        result: dict,
    ) -> Optional[dict]:
        session_id = tool_context.session.id if tool_context.session else None
        if not session_id:
            return None
            
        span = self._tool_spans.pop(session_id, None)
        if not span:
            return None

        try:
            # Update v2 Span
            span.update(
                output=result
            )
        except Exception as exc:
            log.warning("LangfuseADKPlugin: failed to log after tool: %s", exc)
        return None

    async def on_tool_error_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        error: Exception,
    ) -> Optional[dict]:
        session_id = tool_context.session.id if tool_context.session else None
        if not session_id:
            return None
            
        span = self._tool_spans.pop(session_id, None)
        if not span:
            return None

        try:
            # Update v2 Span with error details
            span.update(
                level="ERROR",
                status_message=str(error),
            )
        except Exception as exc:
            log.warning("LangfuseADKPlugin: failed to log on tool error: %s", exc)
        return None
