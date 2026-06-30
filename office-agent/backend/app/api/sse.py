"""SSE (Server-Sent Events) 工具函数。

用于实现流式响应。
"""

from __future__ import annotations

import json
from typing import Any


def format_sse_event(event_type: str, data: Any) -> str:
    """格式化单个 SSE 事件。"""
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {data}\n\n"
