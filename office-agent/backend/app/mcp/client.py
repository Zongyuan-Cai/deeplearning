from __future__ import annotations

import uuid
from typing import Any, Dict, List

from app.mcp.registry import MCPServerRegistry
from app.mcp.types import ToolCall, ToolResult, ToolSchema


class LocalMCPClient:
    def __init__(self, registry: MCPServerRegistry) -> None:
        self.registry = registry

    def list_tools(self) -> List[ToolSchema]:
        return self.registry.list_tools()

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        server = self.registry.get_server_by_tool_name(tool_name)
        if server is None:
            return ToolResult(
                call_id=str(uuid.uuid4()),
                tool_name=tool_name,
                success=False,
                content=None,
                error=f"Tool not found: {tool_name}",
            )

        call = ToolCall(
            id=str(uuid.uuid4()),
            name=tool_name,
            arguments=arguments,
        )
        return server.call_tool(call)