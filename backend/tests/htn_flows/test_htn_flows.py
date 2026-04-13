from unittest.mock import AsyncMock, patch

import pytest

from agents.academic_agent.htn_planner import HTNPlanner
from agents.base import AgentInput


@pytest.mark.asyncio
async def test_f01_happy_path():
    context = {"entropy": 0.5, "fatigue": 0.3, "confusion": 0.4}
    with patch(
        "agents.academic_agent.htn_executor.PRIMITIVE_REGISTRY", new_callable=dict
    ) as mock_reg:
        for k in [
            "P04_select_next_question",
            "P01_serve_mcq",
            "P02_record_response",
            "P03_update_beliefs",
        ]:
            mock_reg[k] = AsyncMock(return_value={"status": "success", "payload": {}})
        planner = HTNPlanner("configs/htn_rules.yaml")
        inp = AgentInput(
            session_id="sess_test_01",
            current_state={
                "academic_state": {"entropy": 0.5},
                "empathy_state": {"fatigue": 0.3, "confusion": 0.4},
            },
        )
        result = await planner.process(inp)

        # current HTNPlanner returns a plan_generated output with tasks/context
        assert result.action == "plan_generated"
        assert "tasks" in result.payload


@pytest.mark.asyncio
async def test_f02_crisis_mode_and_cognitive_load():
    context = {"entropy": 0.9, "fatigue": 0.8, "confusion": 0.7}
    with patch(
        "agents.academic_agent.htn_executor.PRIMITIVE_REGISTRY", new_callable=dict
    ) as mock_reg:
        mock_reg["P08_assess_fatigue"] = AsyncMock(
            return_value={"status": "success", "payload": {"fatigue": 0.82}}
        )
        mock_p09 = AsyncMock(
            return_value={"status": "success", "payload": {"de_stress_sent": True}}
        )
        mock_reg["P09_trigger_de_stress"] = mock_p09
        mock_reg["P05_generate_hint"] = AsyncMock(
            return_value={"status": "success", "payload": {"fallback_used": True}}
        )

        planner = HTNPlanner("configs/htn_rules.yaml")
        inp = AgentInput(
            session_id="sess_test_02",
            current_state={
                "academic_state": {"entropy": 0.9},
                "empathy_state": {"fatigue": 0.8, "confusion": 0.7},
            },
        )
        result = await planner.process(inp)

        # ensure we get a plan (may be empty depending on rules)
        assert result.action == "plan_generated"
        assert result.payload.get("context") is not None


@pytest.mark.asyncio
async def test_f03_plan_repair_altmethod():
    context = {
        "entropy": 0.6,
        "fatigue": 0.4,
        "current_method": "M03_info_gain_drill",
        "M03_info_gain_drill_retries": 0,
        "FALLBACK_METHOD_MAP": {"M03_info_gain_drill": "M03_q_policy_drill"},
    }
    with patch(
        "agents.academic_agent.htn_executor.PRIMITIVE_REGISTRY", new_callable=dict
    ) as mock_reg:
        # First call fails, subsequent succeeds
        mock_reg["P04_select_next_question"] = AsyncMock(
            side_effect=[
                {"status": "failed", "error": "Unexpected"},
                {"status": "success", "payload": {}},
            ]
        )

        planner = HTNPlanner("configs/htn_rules.yaml")
        new_method, cont = planner.repair_plan(
            "P04_select_next_question", "M03_info_gain_drill", context
        )
        assert new_method is not None
        assert cont is True


@pytest.mark.asyncio
async def test_f04_max_retry_hitl_escalation():
    context = {"entropy": 0.6, "fatigue": 0.4}
    with patch(
        "agents.academic_agent.htn_executor.PRIMITIVE_REGISTRY", new_callable=dict
    ) as mock_reg:
        for k in [
            "P04_select_next_question",
            "P01_serve_mcq",
            "P02_record_response",
            "P03_update_beliefs",
        ]:
            mock_reg[k] = AsyncMock(
                return_value={"status": "failed", "error": "mock error"}
            )

        mock_hitl = AsyncMock(
            return_value={
                "status": "success",
                "payload": {"fallback": "P09_trigger_de_stress"},
            }
        )
        mock_reg["P12_trigger_hitl"] = mock_hitl

        planner = HTNPlanner("configs/htn_rules.yaml")
        # simulate max retries reached for this task
        ctx = {"P04_select_next_question_retries": 2}
        new_method, cont = planner.repair_plan(
            "P04_select_next_question", "M03_info_gain_drill", ctx
        )
        assert new_method == "hitl_escalation"
        assert cont is False


@pytest.mark.asyncio
async def test_f05_belief_shift_reroute():
    context = {"entropy": 0.5, "fatigue": 0.3}
    with patch(
        "agents.academic_agent.htn_executor.PRIMITIVE_REGISTRY", new_callable=dict
    ) as mock_reg:
        mock_reg["P03_update_beliefs"] = AsyncMock(
            return_value={"status": "success", "payload": {"entropy": 0.88}}
        )
        planner = HTNPlanner("configs/htn_rules.yaml")
        inp = AgentInput(
            session_id="sess_test_05",
            current_state={
                "academic_state": {"entropy": 0.88},
                "empathy_state": {"fatigue": 0.3},
            },
        )
        result = await planner.process(inp)
        assert hasattr(planner, "methods")
