from __future__ import annotations

from datetime import datetime

import pytest

from core import state_manager as state_manager_module


class _SupabaseClientStub:
    def table(self, name: str):
        del name
        raise AssertionError("DB table access is not expected in this unit test")


class _WSManagerStub:
    async def send_to_session(self, session_id: str, payload: str) -> None:
        del session_id, payload


@pytest.mark.asyncio
async def test_load_or_init_rehydrates_from_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(
        state_manager_module,
        "create_client",
        lambda *args, **kwargs: _SupabaseClientStub(),
    )

    async def _session_stub(**kwargs):
        assert kwargs["session_id"] == "sess-rehydrate"
        assert kwargs["student_id"] == "student-1"
        return {
            "id": "sess-rehydrate",
            "status": "active",
            "last_question_index": 4,
            "total_questions": 10,
            "progress_percent": 40,
            "last_interaction_at": "2026-04-17T10:30:00+00:00",
            "state_snapshot": {
                "step": 4,
                "mode": "exam_prep",
                "user_classification_level": "advanced",
                "pause_state": True,
                "pause_reason": "afk",
                "off_topic_counter": 2,
                "hitl_pending": True,
                "academic_state": {"belief_dist": {"H03_Chain": 0.6}},
                "empathy_state": {"fatigue": 0.3},
                "strategy_state": {
                    "mode": "exam_prep",
                    "classification_level": "advanced",
                    "last_question_index": 4,
                    "total_questions": 10,
                    "progress_percent": 40,
                },
            },
        }

    monkeypatch.setattr(
        state_manager_module,
        "get_learning_session_by_id",
        _session_stub,
    )

    manager = state_manager_module.StateManager(
        supabase_url="https://example.supabase.co",
        supabase_key="test-key",
        ws_manager=_WSManagerStub(),
    )
    manager.register_session_context(
        session_id="sess-rehydrate",
        student_id="student-1",
        access_token="token",
    )

    state = await manager.load_or_init("sess-rehydrate")

    assert state.step == 4
    assert state.mode == "exam_prep"
    assert state.user_classification_level == "advanced"
    assert state.pause_state is True
    assert state.pause_reason == "afk"
    assert state.off_topic_counter == 2
    assert state.hitl_pending is True
    assert state.strategy_state["last_question_index"] == 4
    assert state.strategy_state["progress_percent"] == 40
    assert isinstance(state.last_interaction_timestamp, datetime)
    assert state.last_interaction_timestamp.tzinfo is not None


@pytest.mark.asyncio
async def test_load_or_init_defaults_when_snapshot_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        state_manager_module,
        "create_client",
        lambda *args, **kwargs: _SupabaseClientStub(),
    )

    async def _session_stub(**kwargs):
        del kwargs
        return None

    monkeypatch.setattr(
        state_manager_module,
        "get_learning_session_by_id",
        _session_stub,
    )

    manager = state_manager_module.StateManager(
        supabase_url="https://example.supabase.co",
        supabase_key="test-key",
        ws_manager=_WSManagerStub(),
    )

    state = await manager.load_or_init("sess-empty")

    assert state.session_id == "sess-empty"
    assert state.step == 0
    assert state.pause_state is False
    assert state.last_interaction_timestamp is None
