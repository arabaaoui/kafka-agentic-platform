"""Unit tests for BaseAgent RAG pre-injection (spec 009 T027 / FR-011, FR-012)."""

from __future__ import annotations

import unittest.mock
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.mission import MissionContext, MissionType


@pytest.fixture
def mission_ctx() -> MissionContext:
    return MissionContext(
        mission_id="TESTCO-PREPROD-INCIDENT-PVC-SATURATION-20260510-001",
        tenant="testco",
        env="preprod",
        cluster="gke-test",
        type=MissionType.INCIDENT,
        subject="pvc-saturation",
    )


def _make_agent(skill_name: str = "kafka_strimzi_expert"):
    """Construct a minimal BaseAgent subclass without hitting ADK or SKILL.md."""
    from agents.base import BaseAgent

    class _TestAgent(BaseAgent):
        SKILL_NAME = skill_name

        def _build_tools(self):
            return []

    with patch.object(BaseAgent, "_load_system_prompt", return_value="mock system prompt"):
        return _TestAgent(model="test-model")


def test_rag_preinject_agents_set():
    """_RAG_PREINJECT_AGENTS must include investigator agents and the consolidator."""
    from agents.base import _RAG_PREINJECT_AGENTS

    assert "kafka_strimzi_expert" in _RAG_PREINJECT_AGENTS
    assert "k8s_gcp_sre" in _RAG_PREINJECT_AGENTS
    assert "prom_alerts_triage" in _RAG_PREINJECT_AGENTS
    assert "evidence_consolidator" in _RAG_PREINJECT_AGENTS
    assert "post_mortem_analyst" not in _RAG_PREINJECT_AGENTS


@pytest.mark.asyncio
async def test_fetch_kb_context_returns_block(mission_ctx):
    """_fetch_kb_context reuses RAGIndex.search + to_context_block."""
    agent = _make_agent("kafka_strimzi_expert")

    with patch("agents.base.RAGIndex") as mock_rag_cls:
        mock_index = MagicMock()
        mock_index.search = AsyncMock(return_value=[MagicMock()])
        mock_index.to_context_block.return_value = "## 📚 KB Context\nrelevant card text"
        mock_rag_cls.return_value = mock_index

        result = await agent._fetch_kb_context(mission_ctx, db=MagicMock())

    assert result == "## 📚 KB Context\nrelevant card text"
    mock_index.search.assert_called_once_with("pvc-saturation INCIDENT")
    mock_index.to_context_block.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_kb_context_empty_when_no_results(mission_ctx):
    """_fetch_kb_context returns '' when RAGIndex finds nothing."""
    agent = _make_agent("kafka_strimzi_expert")

    with patch("agents.base.RAGIndex") as mock_rag_cls:
        mock_index = MagicMock()
        mock_index.search = AsyncMock(return_value=[])
        mock_index.to_context_block.return_value = ""
        mock_rag_cls.return_value = mock_index

        result = await agent._fetch_kb_context(mission_ctx, db=MagicMock())

    assert result == ""


@pytest.mark.asyncio
async def test_fetch_kb_context_search_failure_propagates(mission_ctx):
    """_fetch_kb_context lets exceptions bubble up (caller wraps in try/except)."""
    agent = _make_agent("kafka_strimzi_expert")

    with patch("agents.base.RAGIndex") as mock_rag_cls:
        mock_index = AsyncMock()
        mock_index.search.side_effect = RuntimeError("DB unreachable")
        mock_rag_cls.return_value = mock_index

        with pytest.raises(RuntimeError, match="DB unreachable"):
            await agent._fetch_kb_context(mission_ctx, db=MagicMock())
