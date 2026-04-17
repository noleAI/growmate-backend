import pytest

from core.tool_registry import ToolDefinition, ToolRegistry


async def _ok_handler(value: int) -> dict[str, int]:
    return {"value": value}


async def _boom_handler() -> dict[str, str]:
    raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_register_get_and_tool_names() -> None:
    registry = ToolRegistry()
    tool = ToolDefinition(
        name="sample_tool",
        description="Sample tool",
        parameters={"type": "object", "properties": {}},
        handler=_ok_handler,
    )

    registry.register(tool)

    assert registry.get("sample_tool") is tool
    assert registry.tool_names == ["sample_tool"]


@pytest.mark.asyncio
async def test_execute_success() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="ok",
            description="OK",
            parameters={"type": "object", "properties": {}},
            handler=_ok_handler,
        )
    )

    result = await registry.execute("ok", value=7)

    assert result == {"value": 7}


@pytest.mark.asyncio
async def test_execute_returns_error_for_missing_tool() -> None:
    registry = ToolRegistry()

    result = await registry.execute("missing")

    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_execute_returns_error_for_missing_handler() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="no_handler",
            description="No handler",
            parameters={"type": "object", "properties": {}},
            handler=None,
        )
    )

    result = await registry.execute("no_handler")

    assert "has no handler" in result["error"]


@pytest.mark.asyncio
async def test_execute_catches_handler_exception() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="boom",
            description="Boom",
            parameters={"type": "object", "properties": {}},
            handler=_boom_handler,
        )
    )

    result = await registry.execute("boom")

    assert result["tool"] == "boom"
    assert "boom" in result["error"]


def test_to_gemini_tools_contains_function_declarations() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="ok",
            description="OK",
            parameters={"type": "object", "properties": {}},
            handler=_ok_handler,
        )
    )

    payload = registry.to_gemini_tools()

    assert isinstance(payload, list)
    assert payload
    declarations = payload[0]["function_declarations"]
    assert declarations[0]["name"] == "ok"
    assert declarations[0]["description"] == "OK"
