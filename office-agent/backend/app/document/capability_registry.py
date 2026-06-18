from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.domain.capability_types import CapabilityType
from app.domain.document_types import DocumentType


class ProviderProtocol(Protocol):
    document_type: DocumentType

    def supports(self, capability: CapabilityType) -> bool:
        ...


@dataclass
class RegisteredProvider:
    document_type: DocumentType
    provider: ProviderProtocol


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    requires_structured_input: bool = False
    cross_file: bool = False
    description: str = ""


@dataclass
class DocumentCapabilityProfile:
    document_type: DocumentType
    declared_capabilities: set[str] = field(default_factory=set)


DEFAULT_CAPABILITY_SPECS: dict[str, CapabilitySpec] = {
    CapabilityType.READ.value: CapabilitySpec(
        name=CapabilityType.READ.value,
        requires_structured_input=False,
        cross_file=False,
        description="Read document content",
    ),
    CapabilityType.EXTRACT.value: CapabilitySpec(
        name=CapabilityType.EXTRACT.value,
        requires_structured_input=False,
        cross_file=False,
        description="Extract structured information",
    ),
    CapabilityType.LOCATE.value: CapabilitySpec(
        name=CapabilityType.LOCATE.value,
        requires_structured_input=True,
        cross_file=False,
        description="Locate target content",
    ),
    CapabilityType.FILL.value: CapabilitySpec(
        name=CapabilityType.FILL.value,
        requires_structured_input=True,
        cross_file=False,
        description="Fill template fields",
    ),
    CapabilityType.UPDATE_TABLE.value: CapabilitySpec(
        name=CapabilityType.UPDATE_TABLE.value,
        requires_structured_input=True,
        cross_file=False,
        description="Update table rows/cells",
    ),
    CapabilityType.SUMMARIZE.value: CapabilitySpec(
        name=CapabilityType.SUMMARIZE.value,
        requires_structured_input=False,
        cross_file=True,
        description="Summarize one or many files",
    ),
    CapabilityType.COMPARE.value: CapabilitySpec(
        name=CapabilityType.COMPARE.value,
        requires_structured_input=False,
        cross_file=True,
        description="Compare files",
    ),
    CapabilityType.VALIDATE.value: CapabilitySpec(
        name=CapabilityType.VALIDATE.value,
        requires_structured_input=True,
        cross_file=False,
        description="Validate output quality",
    ),
    CapabilityType.WRITE.value: CapabilitySpec(
        name=CapabilityType.WRITE.value,
        requires_structured_input=True,
        cross_file=False,
        description="Write output file",
    ),
    CapabilityType.SCAN_TEMPLATE.value: CapabilitySpec(
        name=CapabilityType.SCAN_TEMPLATE.value,
        requires_structured_input=False,
        cross_file=False,
        description="Scan template placeholders",
    ),
}


DEFAULT_DOCUMENT_CAPABILITY_MATRIX: dict[DocumentType, set[str]] = {
    DocumentType.WORD: {
        "read",
        "extract",
        "locate",
        "fill",
        "validate",
        "write",
        "compare",
    },
    DocumentType.EXCEL: {
        "read",
        "extract",
        "compare",
        "write",
        "locate",
        "fill",
        "update_table",
        "validate",
    },
    DocumentType.PDF: {
        "read",
        "extract",
        "summarize",
        "locate",
        "fill",
        "validate",
        "write",
        "scan_template",
    },
    DocumentType.PPT: {
        "read",
        "extract",
        "summarize",
        "locate",
        "fill",
        "validate",
        "write",
        "scan_template",
    },
    DocumentType.TEXT: {
        "read",
        "extract",
        "summarize",
        "compare",
        "locate",
        "fill",
        "validate",
        "write",
        "scan_template",
    },
}


class CapabilityRegistry:
    def __init__(self) -> None:
        self._providers: dict[DocumentType, ProviderProtocol] = {}
        self._capability_specs: dict[str, CapabilitySpec] = dict(DEFAULT_CAPABILITY_SPECS)
        self._document_profiles: dict[DocumentType, DocumentCapabilityProfile] = {
            doc_type: DocumentCapabilityProfile(document_type=doc_type, declared_capabilities=set(capabilities))
            for doc_type, capabilities in DEFAULT_DOCUMENT_CAPABILITY_MATRIX.items()
        }

    def register_provider(self, provider: ProviderProtocol) -> None:
        self._providers[provider.document_type] = provider

    def register_capability_spec(self, spec: CapabilitySpec) -> None:
        self._capability_specs[spec.name] = spec

    def register_document_profile(self, document_type: DocumentType, capabilities: set[str]) -> None:
        self._document_profiles[document_type] = DocumentCapabilityProfile(
            document_type=document_type,
            declared_capabilities=set(capabilities),
        )

    def get_provider(self, document_type: DocumentType) -> ProviderProtocol | None:
        return self._providers.get(document_type)

    def require_provider(self, document_type: DocumentType) -> ProviderProtocol:
        provider = self.get_provider(document_type)
        if provider is None:
            raise ValueError(f"No provider registered for document type: {document_type}")
        return provider

    def supports(self, document_type: DocumentType, capability: CapabilityType) -> bool:
        provider = self.get_provider(document_type)
        if provider is None:
            return False

        declared = self.list_declared_capabilities(document_type)
        if capability.value not in declared:
            return False
        return provider.supports(capability)

    def list_supported_document_types(self) -> list[DocumentType]:
        return list(self._providers.keys())

    def list_supported_capabilities(self, document_type: DocumentType) -> list[str]:
        provider = self.get_provider(document_type)
        if provider is None:
            return []

        declared = self.list_declared_capabilities(document_type)
        available = [cap.value for cap in CapabilityType if provider.supports(cap)]
        return [cap for cap in available if cap in declared]

    def list_declared_capabilities(self, document_type: DocumentType) -> list[str]:
        profile = self._document_profiles.get(document_type)
        if profile is None:
            return []
        return sorted(profile.declared_capabilities)

    def capability_requires_structured_input(self, capability: str) -> bool:
        spec = self._capability_specs.get(capability)
        return bool(spec.requires_structured_input) if spec else False

    def capability_can_cross_file(self, capability: str) -> bool:
        spec = self._capability_specs.get(capability)
        return bool(spec.cross_file) if spec else False

    def list_capability_specs(self) -> dict[str, dict]:
        return {
            name: {
                "requires_structured_input": spec.requires_structured_input,
                "cross_file": spec.cross_file,
                "description": spec.description,
            }
            for name, spec in self._capability_specs.items()
        }

    def export_for_prompt(self, allowed_actions: set[str] | None = None) -> dict:
        allowed = {str(item).strip().lower() for item in (allowed_actions or set()) if str(item).strip()}

        by_document_type: dict[str, list[str]] = {}
        declared_support_matrix: dict[str, list[str]] = {}
        for doc_type in self.list_supported_document_types():
            supported = self.list_supported_capabilities(doc_type)
            declared = self.list_declared_capabilities(doc_type)
            if allowed:
                supported = [item for item in supported if item in allowed]
                declared = [item for item in declared if item in allowed]
            by_document_type[doc_type.value] = supported
            declared_support_matrix[doc_type.value] = declared

        capability_specs = self.list_capability_specs()
        if allowed:
            capability_specs = {name: spec for name, spec in capability_specs.items() if name in allowed}

        return {
            "by_document_type": by_document_type,
            "declared_support_matrix": declared_support_matrix,
            "capability_specs": capability_specs,
        }


_global_registry: CapabilityRegistry | None = None


def get_capability_registry() -> CapabilityRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = CapabilityRegistry()
    return _global_registry
