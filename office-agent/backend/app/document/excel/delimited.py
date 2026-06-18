from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from openpyxl.utils.cell import coordinate_to_tuple

from app.domain.capability_types import CapabilityType
from app.document.providers.base import ProviderResult


class DelimitedSpreadsheetHandler:
    def __init__(self, *, provider_name: str, document_type: str, mapper: Any) -> None:
        self.provider_name = provider_name
        self.document_type = document_type
        self.mapper = mapper

    @staticmethod
    def supports(file_path: str) -> bool:
        return Path(file_path).suffix.lower() in {".csv", ".tsv"}

    def read(self, file_path: str, *, max_preview_rows: int = 10) -> ProviderResult:
        rows = self._read_rows(file_path)
        return self._ok(
            message="Delimited spreadsheet read successfully",
            capability=CapabilityType.READ,
            data={
                "sheet_names": ["Sheet1"],
                "preview": {"Sheet1": {"preview": rows[:max_preview_rows], "range": "A1"}},
            },
            file_path=file_path,
        )

    def extract(
        self,
        file_path: str,
        *,
        headers: list[str] | None = None,
        target_fields: list[str] | None = None,
    ) -> ProviderResult:
        rows = self._read_rows(file_path)
        headers = headers or []
        target_fields = target_fields or []
        if headers:
            records = self.records_from_rows(rows, headers)
            mapped_records = self.mapper.map_rows(records, target_fields) if target_fields else records
            return self._ok(
                message="Delimited spreadsheet extracted by headers",
                capability=CapabilityType.EXTRACT,
                data={
                    "sheet_name": "Sheet1",
                    "mode": "header_table",
                    "headers": headers,
                    "records": mapped_records,
                },
                file_path=file_path,
            )

        return self._ok(
            message="Delimited spreadsheet extracted successfully",
            capability=CapabilityType.EXTRACT,
            data={"sheet_name": "Sheet1", "mode": "used_range", "values": rows[:50]},
            file_path=file_path,
        )

    def update_table(
        self,
        file_path: str,
        *,
        headers: list[str],
        rows: list[dict[str, Any]],
        output_path: str,
    ) -> ProviderResult:
        existing_rows = self._read_rows(file_path)
        header_index = self.find_header_index(existing_rows, headers)
        if header_index is None:
            return ProviderResult.fail(
                message=f"Headers not found in delimited spreadsheet: {headers}",
                error_code="EXCEL_HEADERS_NOT_FOUND",
                capability=CapabilityType.UPDATE_TABLE.value,
                provider=self.provider_name,
                document_type=self.document_type,
            )

        normalized_headers = [str(value or "") for value in existing_rows[header_index]]
        for record in rows:
            existing_rows.append([record.get(header) for header in normalized_headers])
        self._write_rows(output_path, existing_rows, source_path=file_path)

        return self._ok(
            message=f"Appended {len(rows)} row(s) to delimited spreadsheet",
            capability=CapabilityType.UPDATE_TABLE,
            data={"sheet_name": "Sheet1", "headers": headers, "rows_appended": len(rows)},
            output_path=output_path,
            file_path=file_path,
        )

    def write(
        self,
        file_path: str,
        *,
        output_path: str,
        cell_values: dict[str, Any] | None = None,
        rows_payload: dict[str, Any] | None = None,
    ) -> ProviderResult:
        rows = self._read_rows(file_path)
        cell_values = cell_values or {}
        if cell_values:
            for cell_ref, value in cell_values.items():
                self.write_cell(rows, cell_ref, value)
            self._write_rows(output_path, rows, source_path=file_path)
            return self._ok(
                message="Delimited spreadsheet cells written successfully",
                capability=CapabilityType.WRITE,
                data={"sheet_name": "Sheet1", "cell_values_count": len(cell_values)},
                output_path=output_path,
                file_path=file_path,
            )

        if rows_payload:
            self.write_rows_payload(rows, rows_payload)
            self._write_rows(output_path, rows, source_path=file_path)
            return self._ok(
                message="Delimited spreadsheet rows written successfully",
                capability=CapabilityType.WRITE,
                data={"sheet_name": "Sheet1", "rows_written": len(rows_payload["rows"])},
                output_path=output_path,
                file_path=file_path,
            )

        self._write_rows(output_path, rows, source_path=file_path)
        return self._ok(
            message="Delimited spreadsheet written successfully",
            capability=CapabilityType.WRITE,
            data={"sheet_name": "Sheet1", "rows_written": 0, "cell_values_count": 0},
            output_path=output_path,
            file_path=file_path,
        )

    def compare(self, left_file_path: str, right_file_path: str) -> ProviderResult:
        left_rows = self._read_rows(left_file_path)
        right_rows = self._read_rows(right_file_path)
        return self._ok(
            message="Delimited spreadsheets compared successfully",
            capability=CapabilityType.COMPARE,
            data={
                "left_file": left_file_path,
                "right_file": right_file_path,
                "identical": left_rows == right_rows,
                "left_rows": len(left_rows),
                "right_rows": len(right_rows),
            },
            file_path=left_file_path,
            raw_format="delimited",
        )

    def records_from_rows(self, rows: list[list[Any]], headers: list[str]) -> list[dict[str, Any]]:
        header_index = self.find_header_index(rows, headers)
        if header_index is None:
            return []
        header_row = [str(value or "") for value in rows[header_index]]
        records: list[dict[str, Any]] = []
        for row in rows[header_index + 1 :]:
            if any(str(value or "").strip() for value in row):
                records.append({header: (row[idx] if idx < len(row) else None) for idx, header in enumerate(header_row)})
        return records

    @staticmethod
    def write_rows_payload(rows: list[list[Any]], rows_payload: dict[str, Any]) -> None:
        start_row = int(rows_payload.get("start_row") or (len(rows) + 1))
        start_col = int(rows_payload["start_col"])
        for r_offset, row in enumerate(rows_payload["rows"]):
            row_idx = start_row - 1 + r_offset
            while len(rows) <= row_idx:
                rows.append([])
            for c_offset, value in enumerate(row):
                col_idx = start_col - 1 + c_offset
                while len(rows[row_idx]) <= col_idx:
                    rows[row_idx].append("")
                rows[row_idx][col_idx] = value

    @staticmethod
    def write_cell(rows: list[list[Any]], cell_ref: str, value: Any) -> None:
        row_idx, col_idx = coordinate_to_tuple(str(cell_ref))
        while len(rows) < row_idx:
            rows.append([])
        row = rows[row_idx - 1]
        while len(row) < col_idx:
            row.append("")
        row[col_idx - 1] = value

    @staticmethod
    def find_header_index(rows: list[list[Any]], headers: list[str]) -> int | None:
        expected = {DelimitedSpreadsheetHandler.normalize_header(header) for header in headers}
        expected.discard("")
        for idx, row in enumerate(rows[:20]):
            values = {DelimitedSpreadsheetHandler.normalize_header(value) for value in row}
            if expected and expected.issubset(values):
                return idx
        return None

    @staticmethod
    def normalize_header(value: Any) -> str:
        return "".join(str(value or "").strip().lower().split())

    @staticmethod
    def delimiter_name(file_path: str) -> str:
        return "tsv" if Path(file_path).suffix.lower() == ".tsv" else "csv"

    @staticmethod
    def delimiter(file_path: str) -> str:
        return "\t" if Path(file_path).suffix.lower() == ".tsv" else ","

    def _read_rows(self, file_path: str) -> list[list[Any]]:
        encodings = ["utf-8-sig", "utf-8", "gb18030", "gbk"]
        last_error: Exception | None = None
        for encoding in encodings:
            try:
                with open(file_path, newline="", encoding=encoding) as f:
                    return [list(row) for row in csv.reader(f, delimiter=self.delimiter(file_path))]
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"Failed to read delimited spreadsheet: {last_error}")

    def _write_rows(self, output_path: str, rows: list[list[Any]], *, source_path: str) -> None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=self.delimiter(source_path))
            writer.writerows(rows)

    def _ok(
        self,
        *,
        message: str,
        capability: CapabilityType,
        data: dict[str, Any],
        file_path: str,
        output_path: str | None = None,
        raw_format: str | None = None,
    ) -> ProviderResult:
        return ProviderResult.ok(
            message=message,
            data=data,
            output_path=output_path,
            capability=capability.value,
            provider=self.provider_name,
            document_type=self.document_type,
            raw={"provider": "excel", "format": raw_format or self.delimiter_name(file_path)},
        )
