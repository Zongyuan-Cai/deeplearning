"""工具注册表：action_type → callable tool。"""

from app.agent.tools.all_tools import ALL_TOOLS

TOOL_MAP: dict[str, object] = {tool.name: tool for tool in ALL_TOOLS}
