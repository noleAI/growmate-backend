from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger("core.tool_registry")


ToolHandler = Callable[..., Awaitable[dict[str, Any]]]


class ToolDefinition(BaseModel):
    """Definition of one callable tool exposed to the reasoning LLM."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ToolRegistry:
    """Central registry for LLM-callable tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    async def execute(self, name: str, **kwargs: Any) -> dict[str, Any]:
        tool = self.get(name)
        if tool is None:
            return {"error": f"Tool '{name}' not found"}

        if tool.handler is None:
            return {"error": f"Tool '{name}' has no handler"}

        try:
            return await tool.handler(**kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tool execution failed for '%s': %s", name, exc)
            return {"error": str(exc), "tool": name}

    def to_gemini_tools(self) -> list[dict[str, Any]]:
        """Convert registry definitions to Gemini function declarations format."""

        declarations: list[dict[str, Any]] = []
        for tool in self._tools.values():
            declarations.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
            )
        return [{"function_declarations": declarations}]

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())
