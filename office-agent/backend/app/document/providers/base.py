from __future__ import annotations

import os
import re
from typing import Any

from pydantic import BaseModel, Field

from app.domain.capability_types import CapabilityType
from app.domain.document_types import DocumentType
from app.document.io_utils import safe_output_path


class ProviderResult(BaseModel):
    success: bool = True
    message: str = ""
    error_code: str | None = None
    capability: str | None = None
    provider: str | None = None
    document_type: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    output_path: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def ok(
        cls,
        *,
        message: str = "",
        data: dict[str, Any] | None = None,
        output_path: str | None = None,
        capability: str | None = None,
        provider: str | None = None,
        document_type: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> "ProviderResult":
        return cls(
            success=True,
            message=message,
            data=data or {},
            output_path=output_path,
            capability=capability,
            provider=provider,
            document_type=document_type,
            raw=raw or {},
        )

    @classmethod
    def fail(
        cls,
        *,
        message: str,
        error_code: str | None = None,
        data: dict[str, Any] | None = None,
        capability: str | None = None,
        provider: str | None = None,
        document_type: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> "ProviderResult":
        return cls(
            success=False,
            message=message,
            error_code=error_code,
            data=data or {},
            capability=capability,
            provider=provider,
            document_type=document_type,
            raw=raw or {},
        )

    @classmethod
    def unsupported(
        cls,
        *,
        operation: str,
        provider: str,
        document_type: str,
    ) -> "ProviderResult":
        return cls.fail(
            message=f"{document_type.upper()} provider does not support '{operation}'",
            error_code="CAPABILITY_NOT_SUPPORTED",
            capability=operation,
            provider=provider,
            document_type=document_type,
        )


class BaseDocumentProvider:
    """
    文档 provider 的最小能力协议：
    1) 通过 SUPPORTED_CAPABILITIES 或重写 supported_capabilities() 声明能力；
    2) 未实现的能力默认返回统一的 unsupported 结果，不抛 NotImplemented；
    3) 所有能力方法统一返回 ProviderResult。
    """

    document_type: DocumentType = DocumentType.UNKNOWN
    SUPPORTED_CAPABILITIES: set[CapabilityType] = set()
    PLACEHOLDER_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"\{\{\s*([^{}\n]+?)\s*\}\}"),
        re.compile(r"<<\s*([^<>\n]+?)\s*>>"),
        re.compile(r"【\s*([^【】\n]+?)\s*】"),
    )

    @property
    def provider_name(self) -> str:
        return self.__class__.__name__

    def supports(self, capability: CapabilityType) -> bool:
        return capability in self.supported_capabilities()

    def supported_capabilities(self) -> set[CapabilityType]:
        return set(self.SUPPORTED_CAPABILITIES)

    def _unsupported(self, operation: str) -> ProviderResult:
        return ProviderResult.unsupported(
            operation=operation,
            provider=self.provider_name,
            document_type=self.document_type.value,
        )

    def read(self, file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("read")

    def extract(self, file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("extract")

    def locate(self, file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("locate")

    def fill(self, file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("fill")

    def update_table(self, file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("update_table")

    def compare(self, left_file_path: str, right_file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("compare")

    def validate(self, file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("validate")

    def write(self, file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("write")

    def scan_template(self, file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("scan_template")

    @classmethod
    def _scan_placeholders(cls, text: str) -> tuple[list[str], list[dict[str, Any]]]:
        fields: set[str] = set()
        occurrences: list[dict[str, Any]] = []

        for pattern in cls.PLACEHOLDER_PATTERNS:
            for match in pattern.finditer(text):
                field = match.group(1).strip()
                fields.add(field)
                occurrences.append(
                    {
                        "field": field,
                        "start": match.start(),
                        "end": match.end(),
                        "matched": match.group(0),
                    }
                )

        return sorted(fields), occurrences

    @staticmethod
    def _normalize_field_values(field_values: Any) -> dict[str, str]:
        def to_text_map(payload: Any) -> dict[str, str]:
            if payload is None:
                return {}

            # Unwrap common nested payload styles.
            if isinstance(payload, dict):
                for nested_key in ("field_values", "mapping", "replacements", "values", "payload", "data"):
                    nested = payload.get(nested_key)
                    if isinstance(nested, (dict, list, tuple)) and nested is not payload:
                        nested_map = to_text_map(nested)
                        if nested_map:
                            return nested_map

                # {"items": [{"key": "...", "value": "..."}]}
                items = payload.get("items")
                if isinstance(items, list):
                    item_map = to_text_map(items)
                    if item_map:
                        return item_map

                result: dict[str, str] = {}
                for k, v in payload.items():
                    if k in {"field_values", "mapping", "replacements", "values", "payload", "data", "items"}:
                        continue
                    if k is None:
                        continue
                    if v is None:
                        continue
                    result[str(k)] = str(v)
                return result

            # [{"key":"x","value":"y"}] or [("x","y")] or [{"x":"y"}]
            if isinstance(payload, (list, tuple)):
                result: dict[str, str] = {}
                for item in payload:
                    if isinstance(item, dict):
                        if "key" in item and "value" in item:
                            key = item.get("key")
                            value = item.get("value")
                            if key is not None and value is not None:
                                result[str(key)] = str(value)
                            continue
                        if len(item) == 1:
                            only_key = next(iter(item.keys()))
                            only_value = item.get(only_key)
                            if only_key is not None and only_value is not None:
                                result[str(only_key)] = str(only_value)
                            continue
                        nested = to_text_map(item)
                        if nested:
                            result.update(nested)
                            continue
                    if isinstance(item, (list, tuple)) and len(item) == 2:
                        key, value = item
                        if key is not None and value is not None:
                            result[str(key)] = str(value)
                return result

            return {}

        return to_text_map(field_values)

    @staticmethod
    def _placeholder_tokens(field_name: str) -> tuple[str, ...]:
        return (
            f"{{{{{field_name}}}}}",
            f"{{{field_name}}}",
            f"<<{field_name}>>",
            f"【{field_name}】",
        )

    @classmethod
    def _replace_placeholders_in_text(cls, text: str, replacements: dict[str, Any]) -> tuple[str, int]:
        normalized = cls._normalize_field_values(replacements)
        replaced = text
        replace_count = 0

        for key, value in normalized.items():
            for token in cls._placeholder_tokens(key):
                count = replaced.count(token)
                if count:
                    replaced = replaced.replace(token, value)
                    replace_count += count
        return replaced, replace_count

    @staticmethod
    def _default_output_path(file_path: str, suffix: str = "_filled") -> str:
        base, ext = os.path.splitext(file_path)
        return f"{base}{suffix}{ext}"

    @staticmethod
    def _safe_output_path(file_path: str, output_path: str | None, suffix: str, avoid_overwrite: bool = True) -> str:
        candidate = output_path or BaseDocumentProvider._default_output_path(file_path, suffix=suffix)
        resolved, _ = safe_output_path(file_path, candidate, avoid_overwrite=avoid_overwrite)
        return resolved


class StubDocumentProvider(BaseDocumentProvider):
    """
    格式存根基类：格式已被识别但功能尚未实现时使用。
    返回结构化的"未支持"响应，而不是抛出异常，实现优雅降级。

    实现新格式时，将对应 Provider 的父类从 StubDocumentProvider
    改为 BaseDocumentProvider，并逐步实现各 capability 方法即可。
    """

    def supported_capabilities(self) -> set[CapabilityType]:
        return set()

    def _unsupported(self, operation: str) -> ProviderResult:
        result = super()._unsupported(operation)
        result.message = f"{self.document_type.value.upper()} 格式暂不支持 [{operation}] 操作，敬请期待。"
        return result

    def read(self, file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("read")

    def extract(self, file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("extract")

    def locate(self, file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("locate")

    def fill(self, file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("fill")

    def update_table(self, file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("update_table")

    def compare(self, left_file_path: str, right_file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("compare")

    def validate(self, file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("validate")

    def write(self, file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("write")

    def scan_template(self, file_path: str, **kwargs) -> ProviderResult:
        return self._unsupported("scan_template")
