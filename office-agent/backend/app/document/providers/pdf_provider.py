from __future__ import annotations

import os
from typing import Any

from app.domain.capability_types import CapabilityType
from app.domain.document_types import DocumentType
from app.document.providers.base import BaseDocumentProvider, ProviderResult

try:
    from pypdf import PdfReader, PdfWriter
except Exception:
    PdfReader = None
    PdfWriter = None


class PdfProvider(BaseDocumentProvider):

    document_type = DocumentType.PDF

    def supported_capabilities(self) -> set[CapabilityType]:
        if not PdfReader:
            return set()
        return {
            CapabilityType.READ,
            CapabilityType.EXTRACT,
            CapabilityType.LOCATE,
            CapabilityType.FILL,
            CapabilityType.VALIDATE,
            CapabilityType.WRITE,
            CapabilityType.SCAN_TEMPLATE,
        }

    def read(self, file_path: str, **kwargs) -> ProviderResult:
        if not PdfReader:
            return ProviderResult(success=False, message="pypdf is not available")
        try:
            reader = PdfReader(file_path)
            total_pages = len(reader.pages)
            start_page = int(kwargs.get("start_page", 1) or 1)
            end_page = int(kwargs.get("end_page", 0) or 0)
            max_pages = int(kwargs.get("max_pages", 5) or 5)
            include_text = bool(kwargs.get("include_text", True))

            start_idx = max(0, start_page - 1)
            hard_end = total_pages if end_page <= 0 else min(total_pages, end_page)
            soft_end = min(hard_end, start_idx + max(1, max_pages))

            pages_preview: list[dict[str, Any]] = []
            for idx in range(start_idx, soft_end):
                page = reader.pages[idx]
                text = page.extract_text() or ""
                pages_preview.append(
                    {
                        "page_index": idx,
                        "char_count": len(text),
                        "preview": text[:1000] if include_text else "",
                    }
                )

            return ProviderResult(
                success=True,
                message="PDF document read successfully",
                data={
                    "page_count": total_pages,
                    "selected_page_range": {
                        "start": start_idx + 1,
                        "end": (soft_end if soft_end > start_idx else (start_idx + 1)),
                    },
                    "preview": pages_preview,
                    "encrypted": bool(reader.is_encrypted),
                },
                raw={"provider": "pdf"},
            )
        except Exception as e:
            return ProviderResult(success=False, message=f"Failed to read pdf document: {e}")

    def extract(self, file_path: str, **kwargs) -> ProviderResult:
        if not PdfReader:
            return ProviderResult(success=False, message="pypdf is not available")
        try:
            reader = PdfReader(file_path)
            pages: list[dict[str, Any]] = []
            full_text_parts: list[str] = []
            for idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                full_text_parts.append(text)
                pages.append({"page_index": idx, "text": text})

            fields = []
            try:
                field_map = reader.get_fields() or {}
                for field_name, field_info in field_map.items():
                    fields.append(
                        {
                            "name": field_name,
                            "value": field_info.get("/V") if isinstance(field_info, dict) else None,
                        }
                    )
            except Exception:
                fields = []

            return ProviderResult(
                success=True,
                message="PDF structured data extracted successfully",
                data={
                    "page_count": len(reader.pages),
                    "pages": pages,
                    "full_text": "\n".join(full_text_parts),
                    "form_fields": fields,
                },
                raw={"provider": "pdf"},
            )
        except Exception as e:
            return ProviderResult(success=False, message=f"Failed to extract pdf data: {e}")

    def locate(self, file_path: str, **kwargs) -> ProviderResult:
        keyword = kwargs.get("keyword")
        if not keyword:
            return ProviderResult(success=False, message="'keyword' is required for pdf locate")
        if not PdfReader:
            return ProviderResult(success=False, message="pypdf is not available")

        try:
            reader = PdfReader(file_path)
            case_sensitive = bool(kwargs.get("case_sensitive", False))
            needle = str(keyword) if case_sensitive else str(keyword).lower()

            matches: list[dict[str, Any]] = []
            for idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                compare = text if case_sensitive else text.lower()
                if needle in compare:
                    matches.append(
                        {
                            "page_index": idx,
                            "preview": text[:500],
                        }
                    )

            return ProviderResult(
                success=True,
                message="PDF locate completed",
                data={
                    "keyword": keyword,
                    "matches": matches,
                },
                raw={"provider": "pdf"},
            )
        except Exception as e:
            return ProviderResult(success=False, message=f"Failed to locate in pdf: {e}")

    def fill(self, file_path: str, **kwargs) -> ProviderResult:
        if not PdfReader or not PdfWriter:
            return ProviderResult(success=False, message="pypdf is not available")

        field_values = self._normalize_field_values(
            kwargs.get("field_values")
            or kwargs.get("mapping")
            or kwargs.get("replacements")
            or kwargs.get("data")
        )
        if not field_values:
            return ProviderResult(success=False, message="'field_values' is required for pdf fill")

        try:
            reader = PdfReader(file_path)
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)

            normalized_values = dict(field_values)
            for page_index in range(len(writer.pages)):
                writer.update_page_form_field_values(writer.pages[page_index], normalized_values)

            output_path = self._safe_output_path(
                file_path,
                kwargs.get("output_path"),
                suffix="_filled",
                avoid_overwrite=bool(kwargs.get("avoid_overwrite", True)),
            )
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                writer.write(f)

            return ProviderResult(
                success=True,
                message="PDF form fields filled successfully",
                data={"field_values_count": len(field_values)},
                output_path=output_path,
                raw={"provider": "pdf"},
            )
        except Exception as e:
            return ProviderResult(success=False, message=f"Failed to fill pdf document: {e}")

    def validate(self, file_path: str, **kwargs) -> ProviderResult:
        if not PdfReader:
            return ProviderResult(success=False, message="pypdf is not available")

        try:
            reader = PdfReader(file_path)
            min_pages = int(kwargs.get("min_pages", 1))
            valid = (not reader.is_encrypted) and len(reader.pages) >= min_pages

            return ProviderResult(
                success=True,
                message="PDF validation completed",
                data={
                    "valid": valid,
                    "encrypted": bool(reader.is_encrypted),
                    "page_count": len(reader.pages),
                    "min_pages": min_pages,
                },
                raw={"provider": "pdf"},
            )
        except Exception as e:
            return ProviderResult(success=False, message=f"Failed to validate pdf document: {e}")

    def write(self, file_path: str, **kwargs) -> ProviderResult:
        if not PdfReader or not PdfWriter:
            return ProviderResult(success=False, message="pypdf is not available")

        try:
            if kwargs.get("field_values"):
                return self.fill(file_path=file_path, **kwargs)

            reader = PdfReader(file_path)
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)

            output_path = self._safe_output_path(
                file_path,
                kwargs.get("output_path"),
                suffix="_written",
                avoid_overwrite=bool(kwargs.get("avoid_overwrite", True)),
            )
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                writer.write(f)

            return ProviderResult(
                success=True,
                message="PDF document written successfully",
                data={"page_count": len(reader.pages)},
                output_path=output_path,
                raw={"provider": "pdf"},
            )
        except Exception as e:
            return ProviderResult(success=False, message=f"Failed to write pdf document: {e}")

    def scan_template(self, file_path: str, **kwargs) -> ProviderResult:
        if not PdfReader:
            return ProviderResult(success=False, message="pypdf is not available")

        try:
            reader = PdfReader(file_path)
            fields: set[str] = set()
            occurrences: list[dict[str, Any]] = []

            for page_idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                page_fields, page_occurrences = self._scan_placeholders(text)
                fields.update(page_fields)
                for item in page_occurrences:
                    occurrences.append(
                        {
                            "page_index": page_idx,
                            **item,
                        }
                    )

            return ProviderResult(
                success=True,
                message="PDF template scanned successfully",
                data={
                    "fields": sorted(fields),
                    "field_count": len(fields),
                    "occurrences": occurrences,
                },
                raw={"provider": "pdf"},
            )
        except Exception as e:
            return ProviderResult(success=False, message=f"Failed to scan pdf template: {e}")
