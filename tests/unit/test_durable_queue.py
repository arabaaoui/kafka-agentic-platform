"""Unit tests for agents/pipeline/durable_queue.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.pipeline.durable_queue import (
    claim_next,
    mark_dead,
    mark_failed,
    mark_processed,
    queue_stats,
)


def _make_session(fetchone_return=None, mappings_return=None):
    session = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = fetchone_return
    if mappings_return is not None:
        result.mappings.return_value.fetchone.return_value = mappings_return
    else:
        result.mappings.return_value.fetchone.return_value = None
    session.execute.return_value = result
    return session, result


# ── claim_next ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_claim_next_returns_none_when_empty():
    session, _ = _make_session(mappings_return=None)
    result = await claim_next(session, "worker-0")
    assert result is None


@pytest.mark.asyncio
async def test_claim_next_returns_dict_when_row_available():
    row = {"id": "abc", "tenant": "carrefour", "source": "jira", "attempts": 1}
    session, _ = _make_session(mappings_return=row)
    result = await claim_next(session, "worker-0")
    assert result == row


@pytest.mark.asyncio
async def test_claim_next_passes_worker_id():
    session, _ = _make_session(mappings_return=None)
    await claim_next(session, "worker-42")
    call_kwargs = session.execute.call_args[0][1]
    assert call_kwargs["worker_id"] == "worker-42"


# ── mark_processed ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_processed_executes_update():
    session, _ = _make_session()
    await mark_processed(session, "trig-1", "mission-1")
    assert session.execute.called


# ── mark_failed ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_failed_resets_claimed_at_when_below_max():
    session = AsyncMock()
    attempts_result = MagicMock()
    attempts_result.fetchone.return_value = (1,)
    reset_result = MagicMock()
    session.execute.side_effect = [attempts_result, reset_result]

    dead = await mark_failed(session, "trig-1", "some error", max_attempts=3)

    assert dead is False
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_mark_failed_delegates_to_mark_dead_when_attempts_exhausted():
    session = AsyncMock()
    attempts_result = MagicMock()
    attempts_result.fetchone.return_value = (3,)
    dead_result = MagicMock()
    session.execute.side_effect = [attempts_result, dead_result]

    dead = await mark_failed(session, "trig-1", "too many failures", max_attempts=3)

    assert dead is True
    # The second call should be mark_dead's UPDATE (last_error='DEAD:...')
    second_call_params = session.execute.call_args_list[1][0][1]
    assert second_call_params["error"].startswith("DEAD:")


@pytest.mark.asyncio
async def test_mark_failed_returns_false_when_no_row():
    session = AsyncMock()
    attempts_result = MagicMock()
    attempts_result.fetchone.return_value = None
    reset_result = MagicMock()
    session.execute.side_effect = [attempts_result, reset_result]

    dead = await mark_failed(session, "trig-missing", "err", max_attempts=3)
    assert dead is False


# ── mark_dead ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_dead_sets_dead_prefix_in_last_error():
    session = AsyncMock()
    result = MagicMock()
    session.execute.return_value = result

    await mark_dead(session, "trig-1", "critical failure")

    call_params = session.execute.call_args[0][1]
    assert call_params["error"].startswith("DEAD:")
    assert "critical failure" in call_params["error"]


@pytest.mark.asyncio
async def test_mark_dead_truncates_long_error():
    session = AsyncMock()
    session.execute.return_value = MagicMock()

    long_error = "x" * 5000
    await mark_dead(session, "trig-1", long_error)

    call_params = session.execute.call_args[0][1]
    assert len(call_params["error"]) <= 4005  # "DEAD:" (5) + 4000


# ── queue_stats ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_queue_stats_returns_correct_dict_shape():
    session = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = (5, 2, 120.5)
    session.execute.return_value = result

    stats = await queue_stats(session)

    assert stats["depth"] == 5
    assert stats["inflight"] == 2
    assert stats["oldest_pending_age_seconds"] == pytest.approx(120.5)


@pytest.mark.asyncio
async def test_queue_stats_returns_zeros_when_empty():
    session = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = (0, 0, None)
    session.execute.return_value = result

    stats = await queue_stats(session)

    assert stats["depth"] == 0
    assert stats["inflight"] == 0
    assert stats["oldest_pending_age_seconds"] is None


@pytest.mark.asyncio
async def test_queue_stats_handles_none_row():
    session = AsyncMock()
    result = MagicMock()
    result.fetchone.return_value = None
    session.execute.return_value = result

    stats = await queue_stats(session)

    assert stats == {"depth": 0, "inflight": 0, "oldest_pending_age_seconds": None}
