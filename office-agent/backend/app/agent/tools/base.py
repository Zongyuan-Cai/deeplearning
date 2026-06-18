"""工具基类 — 将 DocumentService 方法包装为 LangChain Tool。"""

from langchain_core.tools import tool


def doc_tool(name: str, description: str, service_method: str):
    """工厂：基于 DocumentService 方法创建 tool。

    Args:
        name: 工具名（对应 action_type canonical name）
        description: LLM 可读的描述
        service_method: DocumentService 上的方法名
    """
    from app.document.service import DocumentService

    svc = DocumentService()

    @tool(name, description=description)
    def _tool_wrapper(file_path: str, filename: str = "", **kwargs) -> dict:
        method = getattr(svc, service_method)
        result = method(file_path=file_path, filename=filename or None, **kwargs)
        return {
            "success": result.success,
            "message": result.message,
            "data": result.data if isinstance(result.data, dict) else {},
            "output_path": result.output_path,
            "error_code": result.error_code,
        }

    return _tool_wrapper
