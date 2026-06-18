from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.mcp.servers.base import BaseMCPServer
from app.mcp.types import ToolSchema


class MCPServerRegistry:
    def __init__(self) -> None:
        self._servers: Dict[str, BaseMCPServer] = {}
        self._tool_to_server: Dict[str, str] = {}

    def register_server(self, server: BaseMCPServer) -> None:
        server_name = server.server_info.name
        self._servers[server_name] = server

        for tool in server.list_tools():
            self._tool_to_server[tool.name] = server_name

    def list_tools(self) -> List[ToolSchema]:
        tools: List[ToolSchema] = []
        for server in self._servers.values():
            tools.extend(server.list_tools())
        return tools

    def get_server_by_tool_name(self, tool_name: str) -> Optional[BaseMCPServer]:
        server_name = self._tool_to_server.get(tool_name)
        if not server_name:
            return None
        return self._servers.get(server_name)