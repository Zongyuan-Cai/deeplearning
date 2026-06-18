from __future__ import annotations

import json
from typing import Any


def parse_capabilities_json(raw_capabilities: str) -> dict[str, Any]:
    try:
        capabilities_dict = json.loads(raw_capabilities) if raw_capabilities else {}
        if isinstance(capabilities_dict, dict):
            return capabilities_dict
    except Exception:
        pass
    return {}


def normalize_file_items(files: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(files or [], start=1):
        if isinstance(item, dict):
            data = dict(item)
        elif hasattr(item, "model_dump"):
            data = item.model_dump()
        elif hasattr(item, "dict"):
            data = item.dict()
        else:
            continue

        file_id = data.get("file_id") or data.get("filename") or f"file_{idx}"
        filename = data.get("filename") or str(file_id)
        path = data.get("path") or ""
        normalized.append(
            {
                "file_id": str(file_id),
                "filename": str(filename),
                "path": str(path),
                **{k: v for k, v in data.items() if k not in {"file_id", "filename", "path"}},
            }
        )
    return normalized

