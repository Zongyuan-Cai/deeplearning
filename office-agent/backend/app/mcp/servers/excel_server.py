from __future__ import annotations

from typing import List

from app.document.providers.base import ProviderResult
from app.document.service import DocumentService
from app.mcp.servers.base import BaseMCPServer
from app.mcp.types import ServerInfo, ToolCall, ToolResult, ToolSchema


class ExcelServer(BaseMCPServer):
    def __init__(self, document_service: DocumentService | None = None):
        super().__init__(ServerInfo(name="excel_server", description="Excel document operations"))
        self.document_service = document_service or DocumentService()

    def list_tools(self) -> List[ToolSchema]:
        return [
            ToolSchema(
                name="excel.read_preview",
                description="Read sheet names and preview rows from an excel file.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "sheet_name": {"type": "string"},
                        "max_rows": {"type": "integer"},
                        "max_cols": {"type": "integer"},
                    },
                    "required": ["file_path"],
                },
            )
        ]

    def call_tool(self, call: ToolCall) -> ToolResult:
        try:
            args = call.arguments

            if call.name == "excel.read_preview":
                file_path = args["file_path"]
                sheet_name = args.get("sheet_name")
                max_rows = int(args.get("max_rows", 30))
                max_cols = int(args.get("max_cols", 20))

                result = self.document_service.read_document(
                    file_path=file_path,
                    sheet_name=sheet_name,
                    max_preview_rows=max_rows,
                    max_preview_cols=max_cols,
                    max_sheets=1 if sheet_name else 3,
                )
                if not result.success:
                    return self._tool_error(call, result)

                data = result.data if isinstance(result.data, dict) else {}
                preview_by_sheet = data.get("preview", {}) if isinstance(data.get("preview"), dict) else {}
                sheets = data.get("sheet_names", []) if isinstance(data.get("sheet_names"), list) else []

                active_sheet = None
                if sheet_name and sheet_name in preview_by_sheet:
                    active_sheet = sheet_name
                elif preview_by_sheet:
                    active_sheet = next(iter(preview_by_sheet.keys()))
                elif sheets:
                    active_sheet = sheets[0]

                raw_preview = []
                if active_sheet and isinstance(preview_by_sheet.get(active_sheet), dict):
                    raw_preview = preview_by_sheet[active_sheet].get("preview", [])

                clipped = [row[:max_cols] for row in raw_preview[:max_rows]]

                return ToolResult(
                    call_id=call.id,
                    tool_name=call.name,
                    success=True,
                    content={
                        "sheet_names": sheets,
                        "active_sheet": active_sheet,
                        "preview": clipped,
                    },
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
