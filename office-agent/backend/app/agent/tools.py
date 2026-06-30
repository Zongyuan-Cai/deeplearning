"""Tool Registry — 管理 Agent 可用的工具。

替代旧的 tools/__init__.py + tools/all_tools.py + tools/base.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.logger import get_logger

logger = get_logger("app.agent.tools")


@dataclass
class ToolDefinition:
    """工具定义。"""
    name: str
    description: str
    parameters_schema: dict[str, Any]
    handler: Callable[..., dict[str, Any]]


class ToolRegistry:
    """工具注册表，管理所有可用工具。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters_schema: dict[str, Any],
        handler: Callable[..., dict[str, Any]],
    ) -> None:
        """注册一个工具。"""
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters_schema=parameters_schema,
            handler=handler,
        )
        logger.debug("Registered tool: %s", name)

    def get_schemas(self) -> list[dict[str, Any]]:
        """返回所有工具的 OpenAI function schema。"""
        schemas = []
        for tool in self._tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters_schema,
                },
            })
        return schemas

    def execute(self, name: str, arguments: dict[str, Any], **kwargs) -> dict[str, Any]:
        """按名称查找并执行工具。"""
        tool = self._tools.get(name)
        if tool is None:
            return {
                "success": False,
                "message": f"Tool not found: {name}",
                "error_code": "TOOL_NOT_FOUND",
            }

        try:
            # 将 kwargs 中的 files 传给工具
            result = tool.handler(**arguments, **kwargs)
            if not isinstance(result, dict):
                return {"success": False, "message": str(result), "data": {}}
            return result
        except Exception as e:
            logger.exception("Tool execution failed: %s", name)
            return {
                "success": False,
                "message": str(e),
                "error_code": "TOOL_EXECUTION_ERROR",
            }


def _read_file(file_path: str, **kwargs) -> dict[str, Any]:
    """读取文档内容和结构。"""
    from app.document.service import DocumentService
    svc = DocumentService()
    result = svc.read_document(file_path=file_path, **kwargs)
    return {
        "success": result.success,
        "message": result.message,
        "data": result.data if isinstance(result.data, dict) else {},
    }


def _extract_data(file_path: str, **kwargs) -> dict[str, Any]:
    """从文档提取结构化数据。"""
    from app.document.service import DocumentService
    svc = DocumentService()
    result = svc.extract_fields(file_path=file_path, **kwargs)
    return {
        "success": result.success,
        "message": result.message,
        "data": result.data if isinstance(result.data, dict) else {},
    }


def _fill_template(file_path: str, **kwargs) -> dict[str, Any]:
    """模板字段填充。"""
    from app.document.service import DocumentService
    svc = DocumentService()
    result = svc.fill_document(file_path=file_path, **kwargs)
    return {
        "success": result.success,
        "message": result.message,
        "data": result.data if isinstance(result.data, dict) else {},
        "output_path": result.output_path,
    }


def _write_file(file_path: str, **kwargs) -> dict[str, Any]:
    """写入文件到输出目录。"""
    from app.document.service import DocumentService
    svc = DocumentService()
    result = svc.write_document(file_path=file_path, **kwargs)
    return {
        "success": result.success,
        "message": result.message,
        "data": result.data if isinstance(result.data, dict) else {},
        "output_path": result.output_path,
    }


def _compare_files(left_file_path: str, right_file_path: str, **kwargs) -> dict[str, Any]:
    """对比两份文档。"""
    from app.document.service import DocumentService
    svc = DocumentService()
    result = svc.compare_documents(left_file_path=left_file_path, right_file_path=right_file_path, **kwargs)
    return {
        "success": result.success,
        "message": result.message,
        "data": result.data if isinstance(result.data, dict) else {},
    }


def _execute_code(code: str, timeout: int = 30, files: list[dict[str, Any]] | None = None, **kwargs) -> dict[str, Any]:
    """在沙箱中执行 Python 代码。"""
    from app.agent.sandbox import execute_code_sandbox
    return execute_code_sandbox(code=code, files=files, timeout=timeout)


def _list_files(files: list[dict[str, Any]] | None = None, **kwargs) -> dict[str, Any]:
    """列出当前会话文件信息。"""
    if not files:
        return {
            "success": True,
            "message": "No files in current session",
            "data": {"files": []},
        }
    file_list = []
    for f in files:
        file_list.append({
            "file_id": f.get("file_id", ""),
            "filename": f.get("filename", ""),
            "path": f.get("path", ""),
        })
    return {
        "success": True,
        "message": f"Found {len(file_list)} files",
        "data": {"files": file_list},
    }


def create_default_registry() -> ToolRegistry:
    """创建默认的工具注册表。"""
    registry = ToolRegistry()

    # read_file
    registry.register(
        name="read_file",
        description="读取文档内容和结构。支持 Word、Excel、PDF、PPT 等格式。",
        parameters_schema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径",
                },
            },
            "required": ["file_path"],
        },
        handler=_read_file,
    )

    # extract_data
    registry.register(
        name="extract_data",
        description="从文档提取结构化数据。用于提取表格、字段等信息。",
        parameters_schema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径",
                },
            },
            "required": ["file_path"],
        },
        handler=_extract_data,
    )

    # fill_template
    registry.register(
        name="fill_template",
        description="将字段值填充到模板文档中。用于生成报告、合同等。",
        parameters_schema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "模板文件路径",
                },
                "field_values": {
                    "type": "object",
                    "description": "字段值映射 {字段名: 值}",
                },
            },
            "required": ["file_path"],
        },
        handler=_fill_template,
    )

    # write_file
    registry.register(
        name="write_file",
        description="将内容写入输出文件。",
        parameters_schema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "输出文件路径",
                },
                "content": {
                    "type": "string",
                    "description": "文件内容",
                },
            },
            "required": ["file_path"],
        },
        handler=_write_file,
    )

    # compare_files
    registry.register(
        name="compare_files",
        description="对比两份文档的差异。",
        parameters_schema={
            "type": "object",
            "properties": {
                "left_file_path": {
                    "type": "string",
                    "description": "第一个文件路径",
                },
                "right_file_path": {
                    "type": "string",
                    "description": "第二个文件路径",
                },
            },
            "required": ["left_file_path", "right_file_path"],
        },
        handler=_compare_files,
    )

    # execute_code
    registry.register(
        name="execute_code",
        description="在沙箱中执行 Python 代码。用于数据分析、计算等任务。",
        parameters_schema={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "要执行的 Python 代码",
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时时间（秒），默认 30",
                },
            },
            "required": ["code"],
        },
        handler=_execute_code,
    )

    # list_files
    registry.register(
        name="list_files",
        description="列出当前会话中的所有文件信息。",
        parameters_schema={
            "type": "object",
            "properties": {},
        },
        handler=_list_files,
    )

    return registry


# 全局默认注册表
default_registry = create_default_registry()
