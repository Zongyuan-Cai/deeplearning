from __future__ import annotations

from typing import List

from app.core.file_store import FileStore
from app.mcp.servers.base import BaseMCPServer
from app.mcp.types import ServerInfo, ToolCall, ToolResult, ToolSchema


class FileServer(BaseMCPServer):
    def __init__(self, file_store: FileStore):
        super().__init__(ServerInfo(name="file_server", description="File operations"))
        self.file_store = file_store

    def list_tools(self) -> List[ToolSchema]:
        return [
            ToolSchema(
                name="file.list_uploaded",
                description="List all uploaded files in current task.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"}
                    },
                    "required": ["task_id"]
                },
            ),
            ToolSchema(
                name="file.get_info",
                description="Get metadata for one uploaded file.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "file_id": {"type": "string"}
                    },
                    "required": ["task_id", "file_id"]
                },
            ),
        ]

    def call_tool(self, call: ToolCall) -> ToolResult:
        try:
            if call.name == "file.list_uploaded":
                files = self.file_store.list_task_files(call.arguments["task_id"])
                return ToolResult(
                    call_id=call.id,
                    tool_name=call.name,
                    success=True,
                    content={"files": files},
                )

            if call.name == "file.get_info":
                info = self.file_store.get_file_info(
                    task_id=call.arguments["task_id"],
                    file_id=call.arguments["file_id"],
                )
                return ToolResult(
                    call_id=call.id,
                    tool_name=call.name,
                    success=True,
                    content=info,
                )

            return ToolResult(
                call_id=call.id,
                tool_name=call.name,
                success=False,
                content=None,
                error=f"Unsupported tool: {call.name}",
            )
        except Exception as e:
            return ToolResult(
                call_id=call.id,
                tool_name=call.name,
                success=False,
                content=None,
                error=str(e),
            )