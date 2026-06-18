from __future__ import annotations

from enum import Enum


def _normalize_key(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.replace("-", "_")
    text = text.replace(" ", "_")
    return text


class CapabilityType(str, Enum):
    READ = "read"
    EXTRACT = "extract"
    LOCATE = "locate"
    FILL = "fill"
    UPDATE_TABLE = "update_table"
    SUMMARIZE = "summarize"
    COMPARE = "compare"
    VALIDATE = "validate"
    WRITE = "write"
    SCAN_TEMPLATE = "scan_template"

    @classmethod
    def aliases(cls) -> dict[str, "CapabilityType"]:
        alias_map: dict[str, CapabilityType] = {}
        for item in cls:
            alias_map[_normalize_key(item.name)] = item
            alias_map[_normalize_key(item.value)] = item

        # Minimal compatibility for legacy plan/action names.
        alias_map.update(
            {
                "read_document": cls.READ,
                "extract_structured_data": cls.EXTRACT,
                "locate_targets": cls.LOCATE,
                "fill_fields": cls.FILL,
                "compare_documents": cls.COMPARE,
                "validate_output": cls.VALIDATE,
                "create_output": cls.WRITE,
                "scan_template_fields": cls.SCAN_TEMPLATE,
            }
        )
        return alias_map

    @classmethod
    def from_any(cls, value: str | "CapabilityType" | None) -> "CapabilityType" | None:
        if isinstance(value, cls):
            return value
        if value is None:
            return None
        key = _normalize_key(str(value))
        return cls.aliases().get(key)

    @classmethod
    def normalize(cls, value: str | "CapabilityType" | None) -> str | None:
        item = cls.from_any(value)
        return item.value if item else None
