from __future__ import annotations

import os
import re
from difflib import unified_diff
from pathlib import Path
from typing import Any

from app.domain.capability_types import CapabilityType
from app.domain.document_types import DocumentType
from app.document.providers.base import BaseDocumentProvider, ProviderResult


class TextProvider(BaseDocumentProvider):

    document_type = DocumentType.TEXT

    def supported_capabilities(self) -> set[CapabilityType]:
        return {
            CapabilityType.READ,
            CapabilityType.EXTRACT,
            CapabilityType.LOCATE,
            CapabilityType.FILL,
            CapabilityType.COMPARE,
            CapabilityType.VALIDATE,
            CapabilityType.WRITE,
            CapabilityType.SCAN_TEMPLATE,
        }

    def read(self, file_path: str, **kwargs) -> ProviderResult:
        try:
            text = self._read_text(file_path)
            lines = text.splitlines()
            line_start = int(kwargs.get("line_start", 1) or 1)
            line_end = int(kwargs.get("line_end", 0) or 0)
            max_chars = int(kwargs.get("max_chars", 0) or 0)

            start_idx = max(0, line_start - 1)
            end_idx = len(lines) if line_end <= 0 else min(len(lines), line_end)
            sliced_lines = lines[start_idx:end_idx]
            sliced_text = "\n".join(sliced_lines)
            if max_chars > 0:
                sliced_text = sliced_text[:max_chars]

            return ProviderResult(
                success=True,
                message="Text document read successfully",
                data={
                    "text": sliced_text,
                    "line_count": len(lines),
                    "char_count": len(text),
                    "selected_line_range": {"start": line_start, "end": line_end if line_end > 0 else len(lines)},
                    "preview": "\n".join(sliced_lines[:20]),
                },
                raw={"provider": "text"},
            )
        except Exception as e:
            return ProviderResult(success=False, message=f"Failed to read text document: {e}")

    def extract(self, file_path: str, **kwargs) -> ProviderResult:
        try:
            text = self._read_text(file_path)
            lines = text.splitlines()
            paragraphs = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]

            headings: list[dict[str, Any]] = []
            if Path(file_path).suffix.lower() == ".md":
                for idx, line in enumerate(lines):
                    stripped = line.lstrip()
                    if stripped.startswith("#"):
                        level = len(stripped) - len(stripped.lstrip("#"))
                        headings.append(
                            {
                                "line_index": idx,
                                "level": level,
                                "title": stripped[level:].strip(),
                            }
                        )

            fields, occurrences = self._scan_placeholders(text)
            return ProviderResult(
                success=True,
                message="Text structured data extracted successfully",
                data={
                    "paragraphs": paragraphs,
                    "headings": headings,
                    "fields": fields,
                    "field_occurrences": occurrences,
                },
                raw={"provider": "text"},
            )
        except Exception as e:
            return ProviderResult(success=False, message=f"Failed to extract text data: {e}")

    def locate(self, file_path: str, **kwargs) -> ProviderResult:
        keyword = kwargs.get("keyword")
        if not keyword:
            return ProviderResult(success=False, message="'keyword' is required for text locate")

        try:
            text = self._read_text(file_path)
            lines = text.splitlines()
            case_sensitive = bool(kwargs.get("case_sensitive", False))
            use_regex = bool(kwargs.get("regex", False))
            max_results = int(kwargs.get("max_results", 200))

            results: list[dict[str, Any]] = []
            if use_regex:
                flags = 0 if case_sensitive else re.IGNORECASE
                pattern = re.compile(str(keyword), flags)
                for line_idx, line in enumerate(lines):
                    for match in pattern.finditer(line):
                        results.append(
                            {
                                "line_index": line_idx,
                                "column_start": match.start(),
                                "column_end": match.end(),
                                "line_text": line,
                                "matched": match.group(0),
                            }
                        )
                        if len(results) >= max_results:
                            break
                    if len(results) >= max_results:
                        break
            else:
                needle = str(keyword) if case_sensitive else str(keyword).lower()
                for line_idx, line in enumerate(lines):
                    line_cmp = line if case_sensitive else line.lower()
                    start = line_cmp.find(needle)
                    while start != -1:
                        end = start + len(needle)
                        results.append(
                            {
                                "line_index": line_idx,
                                "column_start": start,
                                "column_end": end,
                                "line_text": line,
                                "matched": line[start:end],
                            }
                        )
                        if len(results) >= max_results:
                            break
                        start = line_cmp.find(needle, end)
                    if len(results) >= max_results:
                        break

            return ProviderResult(
                success=True,
                message="Text locate completed",
                data={
                    "keyword": keyword,
                    "case_sensitive": case_sensitive,
                    "regex": use_regex,
                    "matches": results,
                },
                raw={"provider": "text"},
            )
        except Exception as e:
            return ProviderResult(success=False, message=f"Failed to locate in text: {e}")

    def fill(self, file_path: str, **kwargs) -> ProviderResult:
        try:
            field_values = self._normalize_field_values(
                kwargs.get("field_values")
                or kwargs.get("mapping")
                or kwargs.get("replacements")
                or kwargs.get("data")
            )
            text = self._read_text(file_path)
            replaced_text, replace_count = self._replace_placeholders_in_text(text, field_values)

            output_path = self._safe_output_path(
                file_path,
                kwargs.get("output_path"),
                suffix="_filled",
                avoid_overwrite=bool(kwargs.get("avoid_overwrite", True)),
            )
            self._write_text(output_path, replaced_text)

            return ProviderResult(
                success=True,
                message="Text document filled successfully",
                data={
                    "field_values_count": len(field_values),
                    "replace_count": replace_count,
                },
                output_path=output_path,
                raw={"provider": "text"},
            )
        except Exception as e:
            return ProviderResult(success=False, message=f"Failed to fill text document: {e}")

    def compare(self, left_file_path: str, right_file_path: str, **kwargs) -> ProviderResult:
        try:
            left_text = self._read_text(left_file_path)
            right_text = self._read_text(right_file_path)

            if left_text == right_text:
                return ProviderResult(
                    success=True,
                    message="Text documents are identical",
                    data={"identical": True, "diff": []},
                    raw={"provider": "text"},
                )

            left_lines = left_text.splitlines()
            right_lines = right_text.splitlines()
            diff = list(
                unified_diff(
                    left_lines,
                    right_lines,
                    fromfile=os.path.basename(left_file_path),
                    tofile=os.path.basename(right_file_path),
                    lineterm="",
                )
            )
            return ProviderResult(
                success=True,
                message="Text documents compared successfully",
                data={"identical": False, "diff": diff[:1000]},
                raw={"provider": "text"},
            )
        except Exception as e:
            return ProviderResult(success=False, message=f"Failed to compare text documents: {e}")

    def validate(self, file_path: str, **kwargs) -> ProviderResult:
        try:
            text = self._read_text(file_path)
            required_keywords: list[str] = kwargs.get("required_keywords", [])
            missing_keywords = [key for key in required_keywords if key not in text]

            must_not_be_empty = bool(kwargs.get("must_not_be_empty", True))
            valid = (not must_not_be_empty or bool(text.strip())) and not missing_keywords

            return ProviderResult(
                success=True,
                message="Text validation completed",
                data={
                    "valid": valid,
                    "empty": len(text.strip()) == 0,
                    "required_keywords": required_keywords,
                    "missing_keywords": missing_keywords,
                },
                raw={"provider": "text"},
            )
        except Exception as e:
            return ProviderResult(success=False, message=f"Failed to validate text document: {e}")

    def write(self, file_path: str, **kwargs) -> ProviderResult:
        try:
            text = kwargs.get("text")
            if text is None:
                text = kwargs.get("content")
            if text is None:
                # Backward-compatible: allow write-through placeholder replacement without explicit text/content.
                replacements = self._normalize_field_values(
                    kwargs.get("field_values") or kwargs.get("mapping") or kwargs.get("replacements")
                )
                if replacements:
                    source_text = self._read_text(file_path)
                    text, _ = self._replace_placeholders_in_text(source_text, replacements)
            if text is None:
                return ProviderResult(success=False, message="'text' or 'content' is required for text write")

            write_mode = str(kwargs.get("write_mode") or "replace").strip().lower()
            separator = str(kwargs.get("separator") or "\n")
            new_text = str(text)
            if write_mode == "append":
                source_text = self._read_text(file_path)
                merged_text = f"{source_text}{separator if source_text and new_text else ''}{new_text}"
            elif write_mode == "prepend":
                source_text = self._read_text(file_path)
                merged_text = f"{new_text}{separator if source_text and new_text else ''}{source_text}"
            else:
                merged_text = new_text

            output_path = self._safe_output_path(
                file_path,
                kwargs.get("output_path"),
                suffix="_written",
                avoid_overwrite=bool(kwargs.get("avoid_overwrite", True)),
            )
            self._write_text(output_path, merged_text)

            return ProviderResult(
                success=True,
                message="Text document written successfully",
                data={
                    "char_count": len(merged_text),
                    "write_mode": write_mode,
                },
                output_path=output_path,
                raw={"provider": "text"},
            )
        except Exception as e:
            return ProviderResult(success=False, message=f"Failed to write text document: {e}")

    def scan_template(self, file_path: str, **kwargs) -> ProviderResult:
        try:
            text = self._read_text(file_path)
            fields, occurrences = self._scan_placeholders(text)
            return ProviderResult(
                success=True,
                message="Text template scanned successfully",
                data={
                    "fields": fields,
                    "field_count": len(fields),
                    "occurrences": occurrences,
                },
                raw={"provider": "text"},
            )
        except Exception as e:
            return ProviderResult(success=False, message=f"Failed to scan text template: {e}")

    @staticmethod
    def _read_text(file_path: str) -> str:
        encodings = ["utf-8", "utf-8-sig", "gb18030", "gbk"]
        last_error: Exception | None = None
        for encoding in encodings:
            try:
                return Path(file_path).read_text(encoding=encoding)
            except Exception as e:
                last_error = e
        raise RuntimeError(f"Unsupported text encoding: {last_error}")

    @staticmethod
    def _write_text(file_path: str, text: str) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
