from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.document.capability_registry import get_capability_registry
from app.domain.capability_types import CapabilityType
from app.domain.document_types import DocumentType, detect_document_type
from app.document.exceptions import CapabilityNotSupported, DocumentServiceError, UnsupportedDocumentType


@dataclass
class RouteRequest:
    capability: CapabilityType
    file_paths: list[str]
    filename: str | None = None
    mode: str = "single"


@dataclass
class RouteResult:
    capability: CapabilityType
    mode: str
    service_method: str
    document_type: DocumentType
    provider: Any | None
    priority: int


class DocumentRouter:
    _SERVICE_METHOD_BY_CAPABILITY = {
        CapabilityType.READ: "read",
        CapabilityType.EXTRACT: "extract",
        CapabilityType.LOCATE: "locate",
        CapabilityType.FILL: "fill",
        CapabilityType.UPDATE_TABLE: "update_table",
        CapabilityType.COMPARE: "compare",
        CapabilityType.VALIDATE: "validate",
        CapabilityType.WRITE: "write",
        CapabilityType.SCAN_TEMPLATE: "scan_template",
        CapabilityType.SUMMARIZE: "summarize_document",
    }

    _PRIORITY_BY_DOCUMENT_TYPE = {
        DocumentType.WORD: 100,
        DocumentType.EXCEL: 90,
        DocumentType.PDF: 80,
        DocumentType.PPT: 70,
        DocumentType.TEXT: 60,
        DocumentType.UNKNOWN: 0,
    }

    def __init__(self) -> None:
        self.registry = get_capability_registry()

    def route(self, request: RouteRequest) -> RouteResult:
        if request.mode not in {"single", "multi"}:
            raise DocumentServiceError(f"Unsupported route mode: {request.mode}")
        if not request.file_paths:
            raise DocumentServiceError("Route request requires at least one file path")

        doc_types = self._resolve_document_types(request.file_paths, request.filename)
        if request.mode == "single":
            target_doc_type = doc_types[0]
        else:
            target_doc_type = self._resolve_multi_mode_doc_type(request.capability, doc_types)

        provider = self._resolve_provider(request.capability, target_doc_type)
        priority = self._priority_of(target_doc_type)
        service_method = self._service_method_of(request.capability)
        return RouteResult(
            capability=request.capability,
            mode=request.mode,
            service_method=service_method,
            document_type=target_doc_type,
            provider=provider,
            priority=priority,
        )

    def _resolve_document_types(self, file_paths: list[str], filename: str | None) -> list[DocumentType]:
        doc_types: list[DocumentType] = []
        for idx, path in enumerate(file_paths):
            probe_name = filename if idx == 0 and filename else path
            doc_type = detect_document_type(filename=probe_name, file_path=path)
            if doc_type == DocumentType.UNKNOWN:
                raise UnsupportedDocumentType(f"Unsupported document type for: {probe_name}")
            doc_types.append(doc_type)
        return doc_types

    def _resolve_multi_mode_doc_type(self, capability: CapabilityType, doc_types: list[DocumentType]) -> DocumentType:
        if not doc_types:
            raise DocumentServiceError("No document types resolved for multi mode")

        if capability == CapabilityType.SUMMARIZE:
            return sorted(set(doc_types), key=self._priority_of, reverse=True)[0]

        if capability == CapabilityType.COMPARE:
            unique = set(doc_types)
            if len(unique) > 1:
                raise DocumentServiceError("compare requires the same document type for all inputs")
            return doc_types[0]

        ranked = sorted(set(doc_types), key=self._priority_of, reverse=True)
        for doc_type in ranked:
            provider = self.registry.get_provider(doc_type)
            if provider and provider.supports(capability):
                return doc_type

        raise CapabilityNotSupported(
            f"No document type in multi-file input supports capability '{capability.value}'"
        )

    def _resolve_provider(self, capability: CapabilityType, document_type: DocumentType):
        if capability == CapabilityType.SUMMARIZE:
            # Summarize is a service-level capability; provider support is optional.
            return self.registry.get_provider(document_type)

        provider = self.registry.require_provider(document_type)
        if not provider.supports(capability):
            raise CapabilityNotSupported(
                f"Document type '{document_type.value}' does not support capability '{capability.value}'"
            )
        return provider

    def _service_method_of(self, capability: CapabilityType) -> str:
        method = self._SERVICE_METHOD_BY_CAPABILITY.get(capability)
        if not method:
            raise CapabilityNotSupported(f"Unsupported capability routing: {capability.value}")
        return method

    def _priority_of(self, document_type: DocumentType) -> int:
        return self._PRIORITY_BY_DOCUMENT_TYPE.get(document_type, 0)
