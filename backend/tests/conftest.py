from unittest.mock import AsyncMock

import pytest

from agents.academic_agent.htn_node import HTNNode


@pytest.fixture
def mock_context():
    return {
        "session_id": "sess_test_01",
        "entropy": 0.5,
        "fatigue": 0.3,
        "confusion": 0.4,
        "max_info_gain": 0.18,
        "hitl_client": AsyncMock(),
        "supabase": AsyncMock(),
        "llm_service": AsyncMock(),
    }


@pytest.fixture
def sample_node():
    return HTNNode(
        task_id="C02_assess_baseline",
        task_type="compound",
        preconditions="entropy < 0.85 AND fatigue < 0.75",
        method_sequence=["P04_select_next_question", "P01_serve_mcq"],
        max_retries=2,
    )
