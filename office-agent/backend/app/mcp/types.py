from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


JsonDict = Dict[str, Any]


@dataclass
class ToolSchema:
    name: str
    description: str
    input_schema: JsonDict


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: JsonDict


@dataclass
class ToolResult:
    call_id: str
    tool_name: str
    success: bool
    content: Any
    error: Optional[str] = None
    metadata: JsonDict = field(default_factory=dict)


@dataclass
class ServerInfo:
    name: str
    version: str = "0.1.0"
    description: str = ""