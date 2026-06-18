"""全部 Agent 工具定义。每个工具对应一个文档操作能力。"""

from app.agent.tools.base import doc_tool

read_document = doc_tool(
    name="read",
    description="读取文档内容与基础结构（段落、表格等）。",
    service_method="read_document",
)

extract_fields = doc_tool(
    name="extract",
    description="从文档中提取结构化字段信息。",
    service_method="extract_fields",
)

fill_fields = doc_tool(
    name="fill",
    description="将字段值填充到模板文档中。",
    service_method="fill_document",
)

write_output = doc_tool(
    name="write",
    description="将内容写入输出文件。",
    service_method="write_document",
)

summarize_content = doc_tool(
    name="summarize",
    description="生成文档摘要。",
    service_method="summarize_document",
)

compare_documents = doc_tool(
    name="compare",
    description="比较两份文档的差异。",
    service_method="compare_documents",
)

locate_targets = doc_tool(
    name="locate",
    description="在文档中定位目标内容的位置。",
    service_method="locate_targets",
)

scan_template_fields = doc_tool(
    name="scan_template",
    description="扫描文档模板中的占位符字段。",
    service_method="scan_template",
)

validate_output = doc_tool(
    name="validate",
    description="验证输出文档的质量和完整性。",
    service_method="validate_document",
)

update_table = doc_tool(
    name="update_table",
    description="更新文档中的表格数据。",
    service_method="update_table",
)

# build_field_mapping 不通过 doc_tool 工厂创建，它调用 LLM 而非 document service
from langchain_core.tools import tool
from app.core.llm_client import LLMClient


@tool
def build_field_mapping(
    source_step_id: str = "",
    target_schema_from_artifact: str = "",
    user_request: str = "",
) -> dict:
    """基于源数据和目标 schema 使用 LLM 构建字段映射。

    此工具需要 ExecutionContext 中的 intermediate_refs 作为上下文。
    实际映射逻辑在 execute 节点中通过 _resolve_mapping_params 完成。
    """
    return {
        "success": True,
        "message": "Field mapping placeholder — resolved in execute node",
        "data": {"source_step_id": source_step_id, "target_schema_from_artifact": target_schema_from_artifact},
    }


ALL_TOOLS = [
    read_document,
    extract_fields,
    fill_fields,
    write_output,
    summarize_content,
    compare_documents,
    locate_targets,
    scan_template_fields,
    validate_output,
    update_table,
    build_field_mapping,
]
