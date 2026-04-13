from unittest.mock import AsyncMock, patch

import pytest

from agents.academic_agent.htn_node import HTNNode, NodeState


@pytest.mark.asyncio
async def test_f04_repair_alt_method_and_retry(sample_node, mock_context):
    """Cover: Repairing → SelectStrategy(AltMethod) → ApplyRepair → RetryNode → Pending"""
    sample_node.retry_count = 0
    mock_context["FALLBACK_METHOD_MAP"] = {
        "M03_info_gain_drill": "M03_q_policy_drill",
    }
    sample_node.method_sequence = ["M03_info_gain_drill"]

    mock_run = AsyncMock(return_value={"status": "success"})
    with patch.object(sample_node, "_select_repair_strategy", return_value="AltMethod"):
        with patch.object(sample_node, "_apply_repair", return_value=True):
            # Patch run at the CLASS level to avoid Pydantic setattr restrictions
            with patch.object(HTNNode, "run", mock_run):
                result = await sample_node._handle_repair(mock_context)

                assert sample_node.retry_count == 1
                assert sample_node.repair_log[-1]["strategy"] == "AltMethod"
                mock_run.assert_called_once_with(mock_context)


@pytest.mark.asyncio
async def test_f05_max_retry_triggers_hitl(sample_node, mock_context):
    """Cover: Repairing → Escalate → HITL_Request → Timeout → Fallback"""
    sample_node.retry_count = 2  # đạt max_retries=2
    sample_node.method_sequence = ["P04_select_next_question"]

    with patch.object(
        sample_node,
        "_trigger_hitl",
        new=AsyncMock(
            return_value={
                "status": "hitl_escalated",
                "payload": {"fallback": "P09_trigger_de_stress"},
            }
        ),
    ) as mock_hitl:
        result = await sample_node._handle_repair(mock_context)

        mock_hitl.assert_called_once_with(mock_context)
        assert result["status"] == "hitl_escalated"
        assert sample_node.state == NodeState.ESCALATING


@pytest.mark.asyncio
async def test_f06_hitl_timeout_fallback(sample_node, mock_context):
    """Cover: HITL_Request → UserDecision(Timeout) → Fallback"""
    mock_hitl_client = AsyncMock()
    mock_context["hitl_client"] = mock_hitl_client
    sample_node.state = NodeState.ESCALATING

    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        result = await sample_node._trigger_hitl(mock_context)

        mock_hitl_client.push.assert_called_once()
        mock_sleep.assert_called_once_with(3)  # hitl_timeout_sec: 3
        assert result["status"] == "hitl_escalated"
        assert result["payload"]["fallback"] == "P09_trigger_de_stress"
