from __future__ import annotations

from typing import Any

from app.domain.capability_types import CapabilityType
from app.domain.document_types import detect_document_type
from app.document.bootstrap import bootstrap_document_providers
from app.document.exceptions import (
    CapabilityNotSupported,
    DocumentProviderError,
    DocumentServiceError,
    UnsupportedDocumentType,
)
from app.document.io_utils import existing_nonempty_file, validate_input_file
from app.document.providers.base import ProviderResult
from app.document.router import DocumentRouter, RouteRequest


class DocumentService:
    def __init__(self) -> None:
        bootstrap_document_providers()
        self.router = DocumentRouter()

    # ===== 统一 capability 接口（推荐） =====
    def read_document(self, file_path: str, filename: str | None = None, **kwargs) -> ProviderResult:
        return self._call_single(
            capability=CapabilityType.READ,
            method_name="read",
            file_path=file_path,
            filename=filename,
            params=kwargs,
        )

    def extract_fields(self, file_path: str, filename: str | None = None, **kwargs) -> ProviderResult:
        return self._call_single(
            capability=CapabilityType.EXTRACT,
            method_name="extract",
            file_path=file_path,
            filename=filename,
            params=kwargs,
        )

    def locate_targets(self, file_path: str, filename: str | None = None, **kwargs) -> ProviderResult:
        return self._call_single(
            capability=CapabilityType.LOCATE,
            method_name="locate",
            file_path=file_path,
            filename=filename,
            params=kwargs,
        )

    def fill_document(self, file_path: str, filename: str | None = None, **kwargs) -> ProviderResult:
        return self._call_single(
            capability=CapabilityType.FILL,
            method_name="fill",
            file_path=file_path,
            filename=filename,
            params=kwargs,
        )

    def compare_documents(
        self,
        left_file_path: str | None = None,
        right_file_path: str | None = None,
        file_paths: list[str] | None = None,
        filename: str | None = None,
        **kwargs,
    ) -> ProviderResult:
        paths = list(file_paths or [])
        if left_file_path:
            paths.insert(0, left_file_path)
        if right_file_path:
            paths.append(right_file_path)

        if len(paths) < 2:
            raise DocumentServiceError("compare_documents requires at least two file paths")

        left = paths[0]
        right = paths[1]

        capability = CapabilityType.COMPARE
        try:
            route = self.router.route(
                RouteRequest(
                    capability=capability,
                    file_paths=[left, right],
                    filename=filename,
                    mode="multi",
                )
            )
            doc_type = route.document_type
            provider = route.provider

            result = self._invoke_provider(
                provider=provider,
                method_name="compare",
                call_kwargs={
                    "left_file_path": left,
                    "right_file_path": right,
                    **kwargs,
                },
                capability=capability,
            )
            return self._normalize_result(
                result=result,
                capability=capability.value,
                mode="multi",
                doc_type=doc_type.value,
                file_paths=[left, right],
            )
        except DocumentServiceError as exc:
            return self._service_error_result(
                exc=exc,
                capability=capability.value,
                doc_type="mixed",
                mode="multi",
                file_paths=[left, right],
            )

    def validate_document(self, file_path: str, filename: str | None = None, **kwargs) -> ProviderResult:
        return self._call_single(
            capability=CapabilityType.VALIDATE,
            method_name="validate",
            file_path=file_path,
            filename=filename,
            params=kwargs,
        )

    def write_document(self, file_path: str, filename: str | None = None, **kwargs) -> ProviderResult:
        return self._call_single(
            capability=CapabilityType.WRITE,
            method_name="write",
            file_path=file_path,
            filename=filename,
            params=kwargs,
        )

    def summarize_document(
        self,
        file_path: str | None = None,
        file_paths: list[str] | None = None,
        filename: str | None = None,
        **kwargs,
    ) -> ProviderResult:
        paths = list(file_paths or [])
        if file_path:
            paths.insert(0, file_path)
        if not paths:
            raise DocumentServiceError("summarize_document requires file_path or file_paths")

        summaries: list[dict[str, Any]] = []

        for idx, path in enumerate(paths):
            read_result = self.read_document(file_path=path, filename=filename, **kwargs)
            if not read_result.success:
                return self._normalize_result(
                    result=read_result,
                    capability=CapabilityType.SUMMARIZE.value,
                    mode="multi" if len(paths) > 1 else "single",
                    doc_type="mixed" if len(paths) > 1 else detect_document_type(filename=filename or path, file_path=path).value,
                    file_paths=paths,
                )

            data = read_result.data if isinstance(read_result.data, dict) else {}
            preview = ""
            for key in ("preview", "text", "full_text"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    preview = value.strip()
                    break

            if not preview:
                preview = str(data)[:2000]

            short = " ".join(preview.split())[:300]
            summaries.append(
                {
                    "index": idx,
                    "file_path": path,
                    "summary": short,
                }
            )

        merged = "\n".join(item["summary"] for item in summaries if item.get("summary"))
        summary_text = merged[:2000]

        return ProviderResult(
            success=True,
            message="Document summary generated",
            data={
                "summary": summary_text,
                "items": summaries,
                "file_count": len(paths),
                "_service": {
                    "capability": CapabilityType.SUMMARIZE.value,
                    "mode": "multi" if len(paths) > 1 else "single",
                    "document_type": "mixed" if len(paths) > 1 else detect_document_type(filename=filename or paths[0], file_path=paths[0]).value,
                    "file_paths": paths,
                },
            },
            raw={"service": "document", "capability": CapabilityType.SUMMARIZE.value},
        )

    # ===== 兼容旧方法名 =====
    def update_table(self, file_path: str, filename: str | None = None, **kwargs):
        return self._call_single(
            capability=CapabilityType.UPDATE_TABLE,
            method_name="update_table",
            file_path=file_path,
            filename=filename,
            params=kwargs,
        )

    def scan_template(self, file_path: str, filename: str | None = None, **kwargs):
        return self._call_single(
            capability=CapabilityType.SCAN_TEMPLATE,
            method_name="scan_template",
            file_path=file_path,
            filename=filename,
            params=kwargs,
        )

    # ===== 内部统一处理 =====
    def _call_single(
        self,
        capability: CapabilityType,
        method_name: str,
        file_path: str,
        filename: str | None,
        params: dict[str, Any],
    ) -> ProviderResult:
        valid, message = validate_input_file(file_path)
        if not valid:
            return ProviderResult.fail(
                message=message,
                error_code="INPUT_FILE_INVALID",
                capability=capability.value,
                document_type=detect_document_type(filename=filename or file_path, file_path=file_path).value,
                data={
                    "_service": {
                        "capability": capability.value,
                        "mode": "single",
                        "document_type": detect_document_type(filename=filename or file_path, file_path=file_path).value,
                        "file_paths": [file_path],
                    }
                },
                raw={"service": "document", "capability": capability.value},
            )

        try:
            route = self.router.route(
                RouteRequest(
                    capability=capability,
                    file_paths=[file_path],
                    filename=filename,
                    mode="single",
                )
            )
            doc_type = route.document_type
            provider = route.provider
            result = self._invoke_provider(
                provider=provider,
                method_name=method_name,
                call_kwargs={"file_path": file_path, **params},
                capability=capability,
            )
            return self._normalize_result(
                result=result,
                capability=capability.value,
                mode="single",
                doc_type=doc_type.value,
                file_paths=[file_path],
            )
        except DocumentServiceError as exc:
            return self._service_error_result(
                exc=exc,
                capability=capability.value,
                doc_type=detect_document_type(filename=filename or file_path, file_path=file_path).value,
                mode="single",
                file_paths=[file_path],
            )

    @staticmethod
    def _invoke_provider(provider, method_name: str, call_kwargs: dict[str, Any], capability: CapabilityType) -> ProviderResult:
        try:
            method = getattr(provider, method_name)
            result = method(**call_kwargs)
            if isinstance(result, ProviderResult):
                return result
            return ProviderResult(
                success=False,
                message=f"Invalid provider response for capability '{capability.value}'",
                raw={"provider_response_type": type(result).__name__},
            )
        except Exception as exc:
            raise DocumentProviderError(
                f"Provider invocation failed for capability '{capability.value}'"
            ) from exc

    @staticmethod
    def _normalize_result(
        result: ProviderResult,
        capability: str,
        mode: str,
        doc_type: str,
        file_paths: list[str],
    ) -> ProviderResult:
        normalized_success = bool(result.success)
        normalized_message = result.message
        normalized_error_code = result.error_code

        if normalized_success and capability in {CapabilityType.WRITE.value, CapabilityType.FILL.value, CapabilityType.UPDATE_TABLE.value}:
            if not existing_nonempty_file(result.output_path):
                normalized_success = False
                normalized_error_code = normalized_error_code or "OUTPUT_FILE_INVALID"
                normalized_message = (
                    f"{normalized_message}; output file is missing or empty: {result.output_path}"
                    if result.output_path
                    else f"{normalized_message}; provider did not return an output file"
                )

        data = dict(result.data) if isinstance(result.data, dict) else {}
        data["_service"] = {
            "capability": capability,
            "mode": mode,
            "document_type": doc_type,
            "file_paths": file_paths,
        }
        raw = dict(result.raw)
        raw["service"] = "document"
        raw["capability"] = capability

        return ProviderResult(
            success=normalized_success,
            message=normalized_message,
            error_code=normalized_error_code,
            capability=result.capability or capability,
            provider=result.provider,
            document_type=result.document_type or doc_type,
            data=data,
            output_path=result.output_path,
            raw=raw,
        )

    @staticmethod
    def _service_error_result(
        *,
        exc: DocumentServiceError,
        capability: str,
        doc_type: str,
        mode: str,
        file_paths: list[str],
    ) -> ProviderResult:
        error_code = "DOCUMENT_SERVICE_ERROR"
        if isinstance(exc, UnsupportedDocumentType):
            error_code = "UNSUPPORTED_DOCUMENT_TYPE"
        elif isinstance(exc, CapabilityNotSupported):
            error_code = "CAPABILITY_NOT_SUPPORTED"
        elif isinstance(exc, DocumentProviderError):
            error_code = "DOCUMENT_PROVIDER_ERROR"

        return ProviderResult.fail(
            message=str(exc),
            error_code=error_code,
            capability=capability,
            document_type=doc_type,
            data={
                "_service": {
                    "capability": capability,
                    "mode": mode,
                    "document_type": doc_type,
                    "file_paths": file_paths,
                }
            },
            raw={"service": "document", "capability": capability},
        )
