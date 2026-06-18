from __future__ import annotations

from typing import Any


def normalize_field_name(field_name: str) -> str:
    return "".join(str(field_name).strip().lower().split())


def map_record_to_fields(record: dict[str, Any], target_fields: list[str]) -> dict[str, Any]:
    source_index = {normalize_field_name(key): value for key, value in record.items()}
    mapped: dict[str, Any] = {}
    for field in target_fields:
        mapped[field] = source_index.get(normalize_field_name(field))
    return mapped
