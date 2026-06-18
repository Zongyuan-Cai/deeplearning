from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any

from app.mcp.types import ToolSchema


@dataclass
class MCPTool:
    schema: ToolSchema
    handler: Callable[..., Any]