from __future__ import annotations

from typing import List

from app.document.providers.base import ProviderResult
from app.document.service import DocumentService
from app.mcp.servers.base import BaseMCPServer
from app.mcp.types import ServerInfo, ToolCall, ToolResult, ToolSchema


class WordServer(BaseMCPServer):
    def __init__(self, document_service: DocumentService | None = None):
        super().__init__(ServerInfo(name="word_server", description="Word document operations"))
        self.document_service = document_service or DocumentService()

    def list_tools(self) -> List[ToolSchema]:
        return [
            ToolSchema(
                name="word.read_text",
                description="Read all plain text paragraphs from a docx file.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"}
                    },
                    "required": ["file_path"]
                },
            ),
            ToolSchema(
                name="word.read_tables",
                description="Read all tables from a docx file and return structured rows.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"}
                    },
                    "required": ["file_path"]
                },
            ),
            ToolSchema(
                name="word.extract_structure",
                description="Extract paragraphs, headings, and tables from a docx file.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"}
                    },
                    "required": ["file_path"]
                },
            ),
            ToolSchema(
                name="word.replace_text",
                description="Replace placeholder text in a docx file and save as a new file.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "replacements": {
                            "type": "object",
                            "additionalProperties": {"type": "string"}
                        },
                        "output_path": {"type": "string"}
                    },
                    "required": ["file_path", "replacements", "output_path"]
                },
            ),
            ToolSchema(
                name="word.append_text",
                description="Append text to the end of a docx file and save as a new file.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "append_text": {"type": "string"},
                        "output_path": {"type": "string"}
                    },
                    "required": ["file_path", "append_text"]
                },
            ),
        ]

    def call_tool(self, call: ToolCall) -> ToolResult:
        try:
            args = call.arguments

            if call.name == "word.read_text":
                result = self.document_service.read_document(file_path=args["file_path"])
                if not result.success:
                    return self._tool_error(call, result)
                data = result.data if isinstance(result.data, dict) else {}
                content = data.get("text", "")
                return ToolResult(
                    call_id=call.id,
                    tool_name=call.name,
                    success=True,
                    content={"text": content},
                )

            if call.name == "word.read_tables":
                result = self.document_service.read_document(file_path=args["file_path"])
                if not result.success:
                    return self._tool_error(call, result)
                data = result.data if isinstance(result.data, dict) else {}
                tables = data.get("tables", [])
                return ToolResult(
                    call_id=call.id,
                    tool_name=call.name,
                    success=True,
                    content={"tables": tables},
                )

            if call.name == "word.extract_structure":
                result = self.document_service.read_document(file_path=args["file_path"])
                if not result.success:
                    return self._tool_error(call, result)
                data = result.data if isinstance(result.data, dict) else {}
                structure = data.get("structure", {})
                return ToolResult(
                    call_id=call.id,
                    tool_name=call.name,
                    success=True,
                    content=structure,
                )

            if call.name == "word.replace_text":
                result = self.document_service.write_document(
                    file_path=args["file_path"],
                    replacements=args["replacements"],
                    output_path=args["output_path"],
                )
                if not result.success:
                    return self._tool_error(call, result)
                data = result.data if isinstance(result.data, dict) else {}
                write_result = data.get("write_result", {})
                return ToolResult(
                    call_id=call.id,
                    tool_name=call.name,
                    success=True,
                    content=write_result,
                )

            if call.name == "word.append_text":
                result = self.document_service.write_document(
                    file_path=args["file_path"],
                    append_text=args["append_text"],
                    output_path=args.get("output_path"),
                    write_mode="append",
                )
                if not result.success:
                    return self._tool_error(call, result)
                data = result.data if isinstance(result.data, dict) else {}
                write_result = data.get("write_result", {})
                return ToolResult(
                    call_id=call.id,
                    tool_name=call.name,
                    success=True,
                    content=write_result,
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

    @staticmethod
    def _tool_error(call: ToolCall, result: ProviderResult) -> ToolResult:
        return ToolResult(
            call_id=call.id,
            tool_name=call.name,
            success=False,
            content=None,
            error=result.message,
        )
