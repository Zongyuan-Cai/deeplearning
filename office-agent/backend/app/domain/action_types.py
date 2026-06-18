from __future__ import annotations

from enum import Enum


def _normalize_key(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.replace("-", "_")
    text = text.replace(" ", "_")
    return text


class ActionType(str, Enum):
    READ_DOCUMENT = "READ_DOCUMENT"
    EXTRACT_STRUCTURED_DATA = "EXTRACT_STRUCTURED_DATA"
    LOCATE_TARGETS = "LOCATE_TARGETS"
    FILL_FIELDS = "FILL_FIELDS"
    UPDATE_TABLE = "UPDATE_TABLE"
    SUMMARIZE_CONTENT = "SUMMARIZE_CONTENT"
    COMPARE_DOCUMENTS = "COMPARE_DOCUMENTS"
    VALIDATE_OUTPUT = "VALIDATE_OUTPUT"
    CREATE_OUTPUT = "CREATE_OUTPUT"
    BUILD_FIELD_MAPPING = "BUILD_FIELD_MAPPING"
    SCAN_TEMPLATE_FIELDS = "SCAN_TEMPLATE_FIELDS"

    @property
    def canonical_name(self) -> str:
        mapping = {
            ActionType.READ_DOCUMENT: "read",
            ActionType.EXTRACT_STRUCTURED_DATA: "extract",
            ActionType.LOCATE_TARGETS: "locate",
            ActionType.FILL_FIELDS: "fill",
            ActionType.UPDATE_TABLE: "update_table",
            ActionType.SUMMARIZE_CONTENT: "summarize",
            ActionType.COMPARE_DOCUMENTS: "compare",
            ActionType.VALIDATE_OUTPUT: "validate",
            ActionType.CREATE_OUTPUT: "write",
            ActionType.BUILD_FIELD_MAPPING: "build_field_mapping",
            ActionType.SCAN_TEMPLATE_FIELDS: "scan_template",
        }
        return mapping[self]

    @classmethod
    def aliases(cls) -> dict[str, "ActionType"]:
        alias_map: dict[str, ActionType] = {}
        for item in cls:
            alias_map[_normalize_key(item.name)] = item
            alias_map[_normalize_key(item.value)] = item
            alias_map[_normalize_key(item.canonical_name)] = item
        return alias_map

    @classmethod
    def from_any(cls, value: str | "ActionType" | None) -> "ActionType" | None:
        if isinstance(value, cls):
            return value
        if value is None:
            return None
        key = _normalize_key(str(value))
        return cls.aliases().get(key)

    @classmethod
    def normalize(cls, value: str | "ActionType" | None) -> str | None:
        item = cls.from_any(value)
        return item.canonical_name if item else None
