import json
import re
from typing import Any, Optional


def extract_json_object(text: str) -> Optional[dict[str, Any]]:
    """
    尽量从 LLM 返回文本中提取 JSON 对象
    支持：
    1. 纯 JSON
    2. ```json ... ``` 代码块
    3. 前后带解释文字
    """
    text = text.strip()

    # 情况1：直接就是 JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 情况2：```json ... ```
    code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block_match:
        candidate = code_block_match.group(1)
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # 情况3：从整段文本里抓第一个 {...}
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        candidate = brace_match.group(0)
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None