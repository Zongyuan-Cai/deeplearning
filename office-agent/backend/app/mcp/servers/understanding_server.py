from __future__ import annotations

from typing import List

from app.core.llm_client import LLMClient
from app.mcp.servers.base import BaseMCPServer
from app.mcp.types import ServerInfo, ToolCall, ToolResult, ToolSchema

class UnderstandingServer(BaseMCPServer):
    def __init__(self, llm_client: LLMClient):
        super().__init__(ServerInfo(name="understanding_server", description="LLM-based understanding tools"))
        self.llm_client = llm_client

    def list_tools(self) -> List[ToolSchema]:
        return [
            ToolSchema(
                name="understanding.summarize",
                description="Summarize text content into a concise structured summary.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "instruction": {"type": "string"}
                    },
                    "required": ["text"]
                },
            ),
            ToolSchema(
                name="understanding.extract_fields",
                description="Extract key fields from text or table content.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "content": {},
                        "instruction": {"type": "string"}
                    },
                    "required": ["content", "instruction"]
                },
            ),
            ToolSchema(
                name="understanding.match_source_to_template",
                description="Match extracted source fields to template placeholders.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "template_placeholders": {"type": "array"},
                        "source_content": {},
                        "instruction": {"type": "string"}
                    },
                    "required": ["template_placeholders", "source_content"]
                },
            ),
        ]

    def call_tool(self, call: ToolCall) -> ToolResult:
        try:
            args = call.arguments

            if call.name == "understanding.summarize":
                summary = self.llm_client.summarize_text(
                    text=args["text"],
                    instruction=args.get("instruction", "")
                )
                return ToolResult(
                    call_id=call.id,
                    tool_name=call.name,
                    success=True,
                    content={"summary": summary},
                )

            if call.name == "understanding.extract_fields":
                data = self.llm_client.extract_fields(
                    content=args["content"],
                    instruction=args["instruction"]
                )
                return ToolResult(
                    call_id=call.id,
                    tool_name=call.name,
                    success=True,
                    content=data,
                )

            if call.name == "understanding.match_source_to_template":
                mapping = self.llm_client.match_source_to_template(
                    template_placeholders=args["template_placeholders"],
                    source_content=args["source_content"],
                    instruction=args.get("instruction", ""),
                )
                return ToolResult(
                    call_id=call.id,
                    tool_name=call.name,
                    success=True,
                    content=mapping,
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