from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.domain.target_selector import TargetSelector


class FieldDataType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    EMAIL = "email"
    PHONE = "phone"


class FieldSourcePolicy(str, Enum):
    AUTO = "auto"
    REQUIRED_FROM_SOURCE = "required_from_source"
    OPTIONAL_FROM_SOURCE = "optional_from_source"
    CONSTANT_DEFAULT = "constant_default"


class FieldRule(BaseModel):
    name: str
    normalized_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    data_type: FieldDataType = FieldDataType.TEXT
    required: bool = False
    allow_empty: bool = True
    default_value: Any = None
    max_length: int | None = None
    regex: str | None = None
    source_policy: FieldSourcePolicy = FieldSourcePolicy.AUTO
    target_selector: TargetSelector | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def canonical_name(self) -> str:
        if self.normalized_name and self.normalized_name.strip():
            return self.normalized_name.strip()
        return self.name.strip().lower().replace(" ", "_")


class FieldConfig(BaseModel):
    fields: list[FieldRule] = Field(default_factory=list)
    strict_mode: bool = False
    unknown_field_policy: str = "allow"  # allow / ignore / reject
    global_selector: TargetSelector = Field(default_factory=TargetSelector)

    def field_names(self) -> list[str]:
        names: list[str] = []
        for item in self.fields:
            names.append(item.name)
            names.extend(item.aliases)
        dedup: list[str] = []
        seen: set[str] = set()
        for n in names:
            key = n.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            dedup.append(n)
        return dedup

    def by_name(self) -> dict[str, FieldRule]:
        index: dict[str, FieldRule] = {}
        for item in self.fields:
            index[item.canonical_name()] = item
            for alias in item.aliases:
                key = alias.strip().lower().replace(" ", "_")
                if key:
                    index[key] = item
        return index


DEFAULT_FIELD_CONFIG = FieldConfig(
    fields=[
        FieldRule(name="姓名", aliases=["name", "客户名称"], required=False, data_type=FieldDataType.TEXT),
        FieldRule(name="年龄", aliases=["age"], required=False, data_type=FieldDataType.NUMBER),
        FieldRule(name="专业", aliases=["major"], required=False, data_type=FieldDataType.TEXT),
        FieldRule(name="班级", aliases=["class"], required=False, data_type=FieldDataType.TEXT),
        FieldRule(name="学号", aliases=["student_id"], required=False, data_type=FieldDataType.TEXT),
        FieldRule(name="手机号", aliases=["phone", "电话"], required=False, data_type=FieldDataType.PHONE),
        FieldRule(name="邮箱", aliases=["email"], required=False, data_type=FieldDataType.EMAIL),
    ],
    strict_mode=False,
    unknown_field_policy="allow",
)

# 兼容旧常量
EXTRACT_FIELD_CANDIDATES = DEFAULT_FIELD_CONFIG.field_names()
