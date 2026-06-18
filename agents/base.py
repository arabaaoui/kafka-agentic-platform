"""BaseAgent — common scaffolding for all platform LlmAgents."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from sqlalchemy import text

from core.mem0_bridge import RAGIndex
from core.mission import MissionContext
from core.plugins import build_plugin_list

log = logging.getLogger(__name__)

# Root of the agents/ directory — resolved at import time.
_AGENTS_DIR = Path(__file__).parent

# Where to write per-agent Markdown outputs.
# Default to /app/agent-outputs if running in container
_OUTPUT_BASE = Path(os.getenv("AGENT_OUTPUT_DIR", "/app/agent-outputs"))

_FR_LANGUAGE_POLICY = """
## Language Policy (PLATFORM_LANG=fr)
- Reason internally in English on tools and decision trees.
- Write your final Markdown output IN PROFESSIONAL FRENCH.
- Keep the following technical terms IN ENGLISH: broker, partition, topic, lag, ISR, URP, \
throughput, leader, follower, KRaft, rolling restart, log compaction, pod, node, PVC, \
namespace, deployment, statefulset, P99, GC pause, CFS throttling.
- Keep all PromQL queries and numeric metric values as-is.
- For confidence, use format: "Niveau de confiance : 85%".
"""

# Injected for expert investigator agents only (kafka_strimzi_expert, k8s_gcp_sre,
# prom_alerts_triage). Encodes the dynamic investigation discipline inspired by
# the gemini-kafka-ops-extension tool-usage-rules.md.
_INVESTIGATION_METHOD = """
## Investigation Method (MANDATORY — apply throughout the entire session)

**Plan-and-Solve** — Before every tool call, state in one sentence:
"I am calling [tool] to verify [specific hypothesis]."
Never jump to a tool call without articulating what you are looking for and why.

**Resilience on errors** — A tool error (timeout, unreachable, non-zero exit,
Prometheus CURL error) is a **valuable finding**, not a reason to stop.
Document it in your report ("unable to verify X because Y"), infer what it
implies structurally, then continue with other available tools.
Never declare "investigation complete" because a single tool failed.

**Deepen on every anomaly** — Every anomaly found (Pending pod, failed task,
abnormal lag, saturated CPU, PVC in error, kubectl timeout) triggers at least
one additional tool call to understand its cause. The stop criterion is NOT
"I have run my 4 mandatory gestures" but:
  (a) root cause identified with at least two concordant pieces of evidence, OR
  (b) all available investigative paths exhausted and information limit reached
      (document as "INCONCLUSIVE — manual investigation required").

**Compose ad-hoc queries** — The shared PromQL library (`promql_kafka`,
`promql_k8s`) is a reference, not a whitelist. When an anomaly requires a metric
not listed there (specific topic name, controller ID, custom alert expression,
new exporter), construct the appropriate PromQL string and pass it directly to
`prom_query`. Reusing library queries is convenient, but never let the library
limit your investigation.

**Auto-Challenge** — Before every conclusion ask yourself:
"Could this evidence mean something else? A Prometheus metric is an indicator,
not ground truth — do I have cross-validation (kubectl logs, a second tool,
a temporal trend)?"
If the answer is no → call a cross-verification tool before concluding.

**Read-only actions = execute them now** — Any prom_query, cluster_health_check,
or kubectl call you consider including in "Recommended Actions" as a verification:
if it is read-only, EXECUTE IT during the investigation and include its result in
the report. Never propose to a human a verification you could perform yourself.
"""

# Agents that receive the investigation method block.
_INVESTIGATOR_AGENTS = {"kafka_strimzi_expert", "k8s_gcp_sre", "prom_alerts_triage"}

# Agents that receive KB/RAG context pre-injected into their task prompt (before any tool call).
_RAG_PREINJECT_AGENTS = _INVESTIGATOR_AGENTS | {"evidence_consolidator"}

# Shared PromQL library from toolkit, keyed by SKILL_NAME.
_SHARED_PROMQL: dict[str, str] = {
    "kafka_strimzi_expert": "promql_kafka",
    "prom_alerts_triage": "promql_kafka",
    "k8s_gcp_sre": "promql_k8s",
}


class BaseAgent:
    """Common base for all platform LlmAgents.

    Subclasses must set ``SKILL_NAME`` (directory under agents/) and
    implement ``_build_tools()``.  The base class handles:
      - SKILL.md loading (hot-reload friendly via watchfiles)
      - Plugin-chain wrapping for every tool call
      - Output persistence (filesystem + Postgres agent_outputs row)
    """

    SKILL_NAME: str = ""

    def __init__(
        self,
        *,
        model: str | None = None,
        tenant_config: Any | None = None,
        **_kwargs: Any,
    ) -> None:
        self._tenant_config = tenant_config
        
        # ── LLM Configuration ─────────────────────────────────────────────────
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "europe-west1")
        api_key = os.getenv("GOOGLE_API_KEY")
        base_model = model or os.getenv("GOOGLE_ADK_MODEL", "gemini-2.5-flash-lite")
        
        # If API Key is present, we use Google AI SDK mode (no project prefix)
        if api_key:
            self._model = base_model
            log.info("%s: using Google AI SDK mode with model: %s", self.SKILL_NAME, self._model)
        # If project is set, format as a Vertex AI resource name
        elif project and not base_model.startswith("projects/"):
            self._model = f"projects/{project}/locations/{location}/publishers/google/models/{base_model}"
            log.info("%s: using Vertex AI model: %s", self.SKILL_NAME, self._model)
        else:
            self._model = base_model
            
        self._skill_path = _AGENTS_DIR / self.SKILL_NAME / "SKILL.md"
        self._system_prompt = self._load_system_prompt()

    # ── System prompt ─────────────────────────────────────────────────────────

    def _load_system_prompt(self) -> str:
        """Load body of SKILL.md and append shared PromQL library from toolkit if applicable."""
        try:
            from kafka_agent_toolkit.skills.loader import load as load_skill, load_shared
            skill = load_skill(self._skill_path)
            body = skill.body
            shared_name = _SHARED_PROMQL.get(self.SKILL_NAME)
            if shared_name:
                try:
                    body = body + "\n" + load_shared(shared_name)
                except FileNotFoundError as exc:
                    log.warning("%s: shared PromQL library not found: %s", self.SKILL_NAME, exc)
            return body
        except Exception as exc:
            log.warning("Could not load SKILL.md for %s: %s", self.SKILL_NAME, exc)
            return f"You are the {self.SKILL_NAME} agent for Kafka InfraOps."

    def reload_skill(self) -> None:
        """Hot-reload system prompt from SKILL.md (called by watchfiles handler)."""
        self._system_prompt = self._load_system_prompt()
        log.info("%s: SKILL.md reloaded", self.SKILL_NAME)

    async def _fetch_kb_context(self, mission_ctx: MissionContext, db: Any) -> str:
        """Return a RAG context block (KB cards + past audits) to prepend to the agent prompt."""
        scope = os.getenv("RAG_SCOPE", "kb,audit").split(",")
        index = RAGIndex(db=db, scope=scope, limit=3)
        results = await index.search(f"{mission_ctx.subject} {mission_ctx.type.value}")
        return index.to_context_block(results)

    # ── Output persistence ────────────────────────────────────────────────────

    def _output_path(self, mission_ctx: MissionContext) -> Path:
        out_dir = _OUTPUT_BASE / mission_ctx.mission_id
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / f"{self.SKILL_NAME}.md"

    async def _persist_output(
        self,
        content: str,
        mission_ctx: MissionContext,
        db_conn: Any,
    ) -> None:
        path = self._output_path(mission_ctx)
        path.write_text(content, encoding="utf-8")
        log.info("%s: wrote output → %s", self.SKILL_NAME, path)

        if db_conn is not None:
            try:
                # Fix: explicit serialization for JSONB compatibility with AsyncConnection
                stmt = text("""
                    INSERT INTO agent_outputs (id, mission_id, agent, output_json, created_at)
                    VALUES (:id, :mission_id, :agent, cast(:output_json AS jsonb), :now)
                """)
                await db_conn.execute(
                    stmt, 
                    {
                        "id": str(uuid.uuid4()),
                        "mission_id": mission_ctx.mission_id,
                        "agent": self.SKILL_NAME,
                        "output_json": json.dumps({"file": str(path), "content": content[:1024*1024]}),
                        "now": datetime.now(timezone.utc),
                    }
                )
            except Exception as exc:
                log.warning("%s: DB persist failed: %s", self.SKILL_NAME, exc)

    # ── ADK runner ────────────────────────────────────────────────────────────

    async def run(
        self,
        mission_ctx: MissionContext,
        prompt: str,
        db_conn: Any = None,
    ) -> str:
        """Run the agent with ``prompt`` and return the Markdown output."""
        from google.adk.tools import FunctionTool
        tools = [FunctionTool(fn) for fn in self._build_tools()]
        now = datetime.now(timezone.utc)

        # ── Safe Manual Interpolation ────────────────────────────────────────
        # We replace {VAR} manually for platform context. 
        # We DO NOT use ADK state to avoid its internal regex which crashes on literal braces.
        mission_type = str(mission_ctx.type.value) if hasattr(mission_ctx.type, "value") else str(mission_ctx.type)
        
        # Get env config for URL/Path injection
        env_cfg = None
        try:
            from core.tenant import TenantRegistry
            tenant_cfg = TenantRegistry.get(mission_ctx.tenant)
            env_cfg = tenant_cfg.envs.get(mission_ctx.env.lower())
        except Exception:
            pass

        replacements = {
            "MISSION_ID": mission_ctx.mission_id,
            "TENANT": mission_ctx.tenant,
            "ENV": mission_ctx.env,
            "CLUSTER": mission_ctx.cluster,
            "SUBJECT": mission_ctx.subject,
            "TYPE": mission_type,
            "TIMESTAMP": now.isoformat(),
            "DATE": now.strftime("%Y-%m-%d"),
            "JIRA_ID": mission_ctx.metadata.get("jira_ticket_id", "N/A"),
            "PROM_URL": env_cfg.prom_url if env_cfg else "N/A",
            "KUBECONFIG": env_cfg.kubeconfig if env_cfg else "N/A",
        }
        
        system_prompt = self._system_prompt
        for key, val in replacements.items():
            # Support both {VAR} and {var}
            system_prompt = system_prompt.replace(f"{{{key}}}", str(val))
            system_prompt = system_prompt.replace(f"{{{key.lower()}}}", str(val))

        if self.SKILL_NAME in _INVESTIGATOR_AGENTS:
            system_prompt = _INVESTIGATION_METHOD + "\n" + system_prompt

        if os.getenv("PLATFORM_LANG", "en").lower() == "fr":
            system_prompt = _FR_LANGUAGE_POLICY + "\n" + system_prompt

        if self.SKILL_NAME in _RAG_PREINJECT_AGENTS:
            _db = db_conn or getattr(mission_ctx, "db_session", None)
            if _db is not None:
                try:
                    kb_ctx = await self._fetch_kb_context(mission_ctx, _db)
                    if kb_ctx:
                        prompt = kb_ctx + "\n" + prompt
                except Exception as exc:
                    log.warning("%s: RAG pre-injection failed (non-fatal): %s", self.SKILL_NAME, exc)

        # IMPORTANT: We pass the system_prompt as is. ADK will not attempt
        # to interpolate it if we don't provide a session state containing
        # variables that match remaining braces.
        agent = LlmAgent(
            name=self.SKILL_NAME,
            model=self._model,
            instruction=system_prompt,
            tools=tools,
        )

        unique_session_id = f"{mission_ctx.mission_id}:{self.SKILL_NAME}"

        session_service = InMemorySessionService()

        from core.plugin_base import _MISSION_CTX_KEY
        adk_plugins = build_plugin_list(
            mission_context=mission_ctx,
            tenant_config=self._tenant_config,
        )

        runner = Runner(
            agent=agent,
            app_name="kafka-agentic-platform",
            session_service=session_service,
            plugins=adk_plugins,
        )

        session_state = {_MISSION_CTX_KEY: mission_ctx}

        await session_service.create_session(
            user_id="system",
            session_id=unique_session_id,
            app_name="kafka-agentic-platform",
            state=session_state,
        )

        output_parts: list[str] = []
        log.info("%s: starting run with session %s", self.SKILL_NAME, unique_session_id)
        try:
            async for event in runner.run_async(
                user_id="system",
                session_id=unique_session_id,
                new_message=Content(parts=[Part(text=prompt)]),
            ):
                if getattr(event, "partial", False):
                    # Skip partial stream chunk events to avoid duplicating output with the final complete messages
                    continue

                if hasattr(event, "content") and event.content and hasattr(event.content, "parts"):
                    for part in event.content.parts:
                        # Extract text if available
                        if hasattr(part, "text") and part.text:
                            output_parts.append(part.text)
                        # Log function calls for visibility in logs
                        elif hasattr(part, "function_call") and part.function_call:
                            log.debug("%s: tool call -> %s", self.SKILL_NAME, part.function_call.name)
        except Exception as exc:
            log.error("%s: runner.run_async fatal error: %s", self.SKILL_NAME, exc, exc_info=True)
            output_parts.append(f"\n\n❌ ERROR: Agent execution failed: {exc}")

        result = "\n".join(output_parts).strip()
        log.info("%s: run completed, output length: %d chars", self.SKILL_NAME, len(result))
        
        # Always persist, even if empty, to signal completion
        await self._persist_output(result, mission_ctx, db_conn)
        return result

    def _build_tools(self) -> list[Callable]:
        """Override in subclasses to return toolkit tool functions."""
        return []
