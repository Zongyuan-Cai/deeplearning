from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List

from app.mcp.types import ToolCall, ToolResult, ToolSchema, ServerInfo


class BaseMCPServer(ABC):
    def __init__(self, server_info: ServerInfo):
        self.server_info = server_info

    @abstractmethod
    def list_tools(self) -> List[ToolSchema]:
        raise NotImplementedError

    @abstractmethod
    def call_tool(self, call: ToolCall) -> ToolResult:
        raise NotImplementedError