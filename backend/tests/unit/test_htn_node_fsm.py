from unittest.mock import AsyncMock, patch

import pytest

from agents.academic_agent.htn_node import NodeState


@pytest.mark.asyncio
async def test_f01_happy_path_state_transitions(sample_node, mock_context):
    """Cover: Pending → CheckPreconditions → Executing → Success → Completed"""
    with patch.object(sample_node, "_check_preconditions", return_value=True):
        with patch.object(
            sample_node,
            "_execute_primitive",
            new=AsyncMock(return_value={"status": "success"}),
        ):
            result = await sample_node.run(mock_context)

            assert result["status"] == "success"
            assert sample_node.state == NodeState.SUCCESS
            assert len(sample_node.repair_log) == 0


@pytest.mark.asyncio
async def test_f02_precondition_fail_triggers_repair(sample_node, mock_context):
    """Cover: CheckPreconditions → Repairing"""
    with patch.object(sample_node, "_check_preconditions", return_value=False):
        with patch.object(
            sample_node,
            "_handle_repair",
            new=AsyncMock(return_value={"status": "repaired"}),
        ):
            result = await sample_node.run(mock_context)
            assert sample_node.state == NodeState.REPAIRING
            assert result["status"] == "repaired"


@pytest.mark.asyncio
async def test_f03_unexpected_outcome_triggers_repair(sample_node, mock_context):
    """Cover: Executing → EvaluateOutcome(Unexpected) → Repairing"""
    with patch.object(sample_node, "_check_preconditions", return_value=True):
        with patch.object(
            sample_node,
            "_execute_primitive",
            new=AsyncMock(return_value={"status": "failed", "reason": "unexpected"}),
        ):
            with patch.object(
                sample_node,
                "_handle_repair",
                new=AsyncMock(return_value={"status": "repaired"}),
            ):
                result = await sample_node.run(mock_context)
                assert sample_node.state == NodeState.REPAIRING
                assert sample_node.retry_count == 1
