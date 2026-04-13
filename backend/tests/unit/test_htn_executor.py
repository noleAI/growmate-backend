import asyncio
from unittest.mock import patch

import pytest

from agents.academic_agent.htn_executor import PRIMITIVE_REGISTRY, execute_primitive


@pytest.mark.asyncio
async def test_valid_primitive_dispatch():
    """Kiểm tra registry gọi đúng hàm async"""

    async def mock_p01(ctx):
        return {"status": "success", "payload": {"q_id": "q1"}}

    with patch.dict(PRIMITIVE_REGISTRY, {"P01_serve_mcq": mock_p01}):
        res = await execute_primitive("P01_serve_mcq", {"topic": "derivative"})
        assert res["status"] == "success"
        assert res["payload"]["q_id"] == "q1"


@pytest.mark.asyncio
async def test_unknown_primitive_returns_failed():
    res = await execute_primitive("P99_invalid_task", {})
    assert res["status"] == "failed"
    assert "Unknown primitive" in res["error"]


@pytest.mark.asyncio
async def test_primitive_exception_handling():
    async def failing_task(ctx):
        raise ValueError("DB connection lost")

    with patch.dict(PRIMITIVE_REGISTRY, {"P02_record_response": failing_task}):
        res = await execute_primitive("P02_record_response", {})
        assert res["status"] == "failed"
        assert "DB connection lost" in res["error"]


@pytest.mark.asyncio
async def test_llm_fallback_trigger():
    """Mô phỏng P05 generate_hint timeout → fallback"""

    async def slow_llm(ctx):
        await asyncio.sleep(5)
        return {"status": "success"}

    with patch.dict(PRIMITIVE_REGISTRY, {"P05_generate_hint": slow_llm}):
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                execute_primitive("P05_generate_hint", {}),
                timeout=0.5,
            )
