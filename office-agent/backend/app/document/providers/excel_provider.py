from __future__ import annotations

from typing import Any

from app.domain.capability_types import CapabilityType
from app.domain.document_types import DocumentType
from app.document.excel.analyzer import ExcelAnalyzer
from app.document.excel.delimited import DelimitedSpreadsheetHandler
from app.document.excel.locator import ExcelLocator
from app.document.excel.mapper import ExcelMapper
from app.document.excel.reader import ExcelReader
from app.document.excel.writer import ExcelWriter
from app.document.providers.base import BaseDocumentProvider, ProviderResult


class ExcelProvider(BaseDocumentProvider):
    document_type = DocumentType.EXCEL
    SUPPORTED_CAPABILITIES = {
        CapabilityType.READ,
        CapabilityType.EXTRACT,
        CapabilityType.LOCATE,
        CapabilityType.FILL,
        CapabilityType.UPDATE_TABLE,
        CapabilityType.VALIDATE,
        CapabilityType.WRITE,
        CapabilityType.COMPARE,
    }

    def __init__(self) -> None:
        self.reader = ExcelReader()
        self.analyzer = ExcelAnalyzer()
        self.locator = ExcelLocator()
        self.mapper = ExcelMapper()
        self.writer = ExcelWriter()
        self.delimited = DelimitedSpreadsheetHandler(
            provider_name=self.provider_name,
            document_type=self.document_type.value,
            mapper=self.mapper,
        )

    def supported_capabilities(self) -> set[CapabilityType]:
        return set(self.SUPPORTED_CAPABILITIES)

    def read(self, file_path: str, **kwargs) -> ProviderResult:
        try:
            if self.delimited.supports(file_path):
                max_preview_rows = int(self._pick(kwargs, ["max_preview_rows", "preview_rows", "max_rows"], 10) or 10)
                return self.delimited.read(file_path, max_preview_rows=max_preview_rows)

            workbook = self.reader.adapter.load(file_path)
            sheets = self.reader.adapter.list_sheets(workbook)
            max_sheets = int(self._pick(kwargs, ["max_sheets", "sheet_limit"], 3) or 3)
            max_preview_rows = int(self._pick(kwargs, ["max_preview_rows", "preview_rows", "max_rows"], 10) or 10)
            max_preview_cols = int(self._pick(kwargs, ["max_preview_cols", "preview_cols", "max_cols"], 5) or 5)
            include_used_range = bool(kwargs.get("include_used_range", False))
            sheet_name = self._pick(kwargs, ["sheet_name", "sheet", "sheetName"], None)

            preview: dict[str, Any] = {}
            selected_sheets: list[str]
            if sheet_name:
                selected_sheets = [str(sheet_name)]
            else:
                selected_sheets = sheets[: max(1, max_sheets)]

            end_col_idx = max(1, max_preview_cols)
            end_col = ""
            idx = end_col_idx
            while idx > 0:
                idx, rem = divmod(idx - 1, 26)
                end_col = chr(65 + rem) + end_col
            range_expr = f"A1:{end_col}{max(1, max_preview_rows)}"

            for current_sheet_name in selected_sheets:
                ws = self.reader.adapter.get_sheet(workbook, current_sheet_name)
                payload: dict[str, Any] = {
                    "preview": self.reader.adapter.read_range(ws, range_expr),
                    "range": range_expr,
                }
                if include_used_range:
                    used = self.reader.adapter.read_used_range(ws)
                    payload["used_range_preview"] = used[:50]
                preview[current_sheet_name] = payload

            return ProviderResult.ok(
                message="Excel document read successfully",
                data={
                    "sheet_names": sheets,
                    "preview": preview,
                },
                capability=CapabilityType.READ.value,
                provider=self.provider_name,
                document_type=self.document_type.value,
                raw={"provider": "excel"},
            )
        except Exception as e:
            return ProviderResult.fail(
                message=f"Failed to read excel document: {e}",
                error_code="EXCEL_READ_FAILED",
                capability=CapabilityType.READ.value,
                provider=self.provider_name,
                document_type=self.document_type.value,
            )

    def extract(self, file_path: str, **kwargs) -> ProviderResult:
        """
        支持三种模式：
        1. 指定 sheet + range
        2. 指定 headers 自动抽表
        3. 默认返回 sheet 预览
        """
        try:
            if self.delimited.supports(file_path):
                headers = self._normalize_header_list(self._pick(kwargs, ["headers", "header_fields", "columns"], None))
                target_fields = self._normalize_header_list(self._pick(kwargs, ["target_fields", "targetFields"], None))
                return self.delimited.extract(file_path, headers=headers, target_fields=target_fields)

            workbook = self.reader.adapter.load(file_path)
            sheet_name = self._pick(kwargs, ["sheet_name", "sheet", "sheetName"], None)
            cell_range = self._pick(kwargs, ["cell_range", "range", "cellRange"], None)
            headers = self._normalize_header_list(self._pick(kwargs, ["headers", "header_fields", "columns"], None))
            target_fields = self._normalize_header_list(self._pick(kwargs, ["target_fields", "targetFields"], None))

            ws = self.reader.adapter.get_sheet(workbook, sheet_name)

            if sheet_name is None:
                sheet_name = ws.title

            if headers:
                records = self.analyzer.extract_table_by_header(
                    file_path=file_path,
                    headers=headers,
                    sheet_name=sheet_name,
                )
                mapped_records = self.mapper.map_rows(records, target_fields) if target_fields else records
                return ProviderResult.ok(
                    message="Excel structured data extracted by headers",
                    data={
                        "sheet_name": sheet_name,
                        "mode": "header_table",
                        "headers": headers,
                        "records": mapped_records,
                    },
                    capability=CapabilityType.EXTRACT.value,
                    provider=self.provider_name,
                    document_type=self.document_type.value,
                    raw={"provider": "excel"},
                )

            if cell_range:
                values = self.reader.adapter.read_range(ws, cell_range)
                return ProviderResult.ok(
                    message="Excel range extracted successfully",
                    data={
                        "sheet_name": sheet_name,
                        "mode": "range",
                        "range": cell_range,
                        "values": values,
                    },
                    capability=CapabilityType.EXTRACT.value,
                    provider=self.provider_name,
                    document_type=self.document_type.value,
                    raw={"provider": "excel"},
                )

            used = self.reader.read_used_range(file_path=file_path, sheet_name=sheet_name)
            return ProviderResult.ok(
                message="Excel used range extracted successfully",
                data={
                    "sheet_name": sheet_name,
                    "mode": "used_range",
                    "values": used[:50],
                },
                capability=CapabilityType.EXTRACT.value,
                provider=self.provider_name,
                document_type=self.document_type.value,
                raw={"provider": "excel"},
            )
        except Exception as e:
            return ProviderResult.fail(
                message=f"Failed to extract excel data: {e}",
                error_code="EXCEL_EXTRACT_FAILED",
                capability=CapabilityType.EXTRACT.value,
                provider=self.provider_name,
                document_type=self.document_type.value,
            )

    def locate(self, file_path: str, **kwargs) -> ProviderResult:
        """
        支持：
        - headers: 查表头行
        - text: 查找某个值出现的位置
        """
        try:
            workbook = self.reader.adapter.load(file_path)
            sheet_name = self._pick(kwargs, ["sheet_name", "sheet", "sheetName"], None)
            headers = self._normalize_header_list(self._pick(kwargs, ["headers", "header_fields", "columns"], None))
            text = self._pick(kwargs, ["text", "keyword", "query"], None)

            ws = self.reader.adapter.get_sheet(workbook, sheet_name)
            if sheet_name is None:
                sheet_name = ws.title

            if headers:
                row_idx = self.locator.find_header_row(
                    file_path=file_path,
                    headers=headers,
                    sheet_name=sheet_name,
                )
                return ProviderResult.ok(
                    message="Excel headers located",
                    data={
                        "sheet_name": sheet_name,
                        "headers": headers,
                        "header_row": row_idx,
                    },
                    capability=CapabilityType.LOCATE.value,
                    provider=self.provider_name,
                    document_type=self.document_type.value,
                    raw={"provider": "excel"},
                )

            if text is not None:
                matches: list[dict[str, Any]] = []
                target = str(text).strip()
                partial = bool(kwargs.get("partial_match", False))
                case_sensitive = bool(kwargs.get("case_sensitive", False))

                cmp_target = target if case_sensitive else target.lower()

                for row in ws.iter_rows():
                    for cell in row:
                        cell_str = "" if cell.value is None else str(cell.value).strip()
                        cmp_cell = cell_str if case_sensitive else cell_str.lower()
                        hit = (cmp_target in cmp_cell) if partial else (cmp_target == cmp_cell)
                        if hit:
                            matches.append(
                                {
                                    "coordinate": cell.coordinate,
                                    "row": cell.row,
                                    "column": cell.column,
                                    "value": cell.value,
                                }
                            )
                return ProviderResult.ok(
                    message="Excel text located",
                    data={
                        "sheet_name": sheet_name,
                        "text": text,
                        "partial_match": partial,
                        "case_sensitive": case_sensitive,
                        "matches": matches,
                    },
                    capability=CapabilityType.LOCATE.value,
                    provider=self.provider_name,
                    document_type=self.document_type.value,
                    raw={"provider": "excel"},
                )

            return ProviderResult.fail(
                message="No locate parameters provided for excel document",
                error_code="EXCEL_LOCATE_PARAMS_MISSING",
                capability=CapabilityType.LOCATE.value,
                provider=self.provider_name,
                document_type=self.document_type.value,
            )
        except Exception as e:
            return ProviderResult.fail(
                message=f"Failed to locate in excel: {e}",
                error_code="EXCEL_LOCATE_FAILED",
                capability=CapabilityType.LOCATE.value,
                provider=self.provider_name,
                document_type=self.document_type.value,
            )

    def map_transform(self, rows: list[dict[str, Any]], target_fields: list[str]) -> ProviderResult:
        try:
            mapped = self.mapper.map_rows(rows=rows, target_fields=target_fields)
            return ProviderResult.ok(
                message="Excel rows mapped successfully",
                data={"mapped_rows": mapped, "target_fields": target_fields},
                capability="mapper",
                provider=self.provider_name,
                document_type=self.document_type.value,
            )
        except Exception as e:
            return ProviderResult.fail(
                message=f"Failed to map excel rows: {e}",
                error_code="EXCEL_MAP_FAILED",
                capability="mapper",
                provider=self.provider_name,
                document_type=self.document_type.value,
            )

    def fill(self, file_path: str, **kwargs) -> ProviderResult:
        """
        支持：
        - cell_values: {"B2": "张三", "C2": 100}
        - rows_payload: {"sheet_name": "...", "start_row": 2, "start_col": 1, "rows": [[...], [...]]}
        """
        # fill 兼容能力：内部转到 write 路径
        return self.write(file_path=file_path, **kwargs)

    def update_table(self, file_path: str, **kwargs) -> ProviderResult:
        """
        按表头追加行，支持两种模式：
        - append_by_header: 传入 headers + rows(list[dict])，自动定位表尾追加
        - 其余参数：退化为 fill()

        params:
        - headers    : list[str]       — 表头列表（用于定位表格）
        - rows       : list[dict]      — 每行数据，key 为表头名
        - sheet_name : str             — 可选，指定 sheet
        - output_path: str             — 输出路径
        """
        headers = self._normalize_header_list(self._pick(kwargs, ["headers", "header_fields", "columns"], None))
        rows = self._normalize_rows_as_records(
            self._pick(kwargs, ["rows", "records", "data_rows", "items"], None),
            headers=headers,
        )

        if not headers or not rows:
            # 无表头模式：退化为 fill
            return self.write(file_path=file_path, **kwargs)

        try:
            if self.delimited.supports(file_path):
                output_path = self._safe_output_path(
                    file_path,
                    kwargs.get("output_path"),
                    suffix="_filled",
                    avoid_overwrite=bool(kwargs.get("avoid_overwrite", True)),
                )
                return self.delimited.update_table(file_path, headers=headers, rows=rows, output_path=output_path)

            workbook = self.reader.adapter.load(file_path)
            output_path = self._safe_output_path(
                file_path,
                kwargs.get("output_path"),
                suffix="_filled",
                avoid_overwrite=bool(kwargs.get("avoid_overwrite", True)),
            )
            sheet_name = self._pick(kwargs, ["sheet_name", "sheet", "sheetName"], None)
            ws = self.reader.adapter.get_sheet(workbook, sheet_name)

            written = self.reader.adapter.append_rows_by_header(ws, headers, rows)
            if written == 0:
                return ProviderResult.fail(
                    message=f"Headers not found in sheet '{ws.title}': {headers}",
                    error_code="EXCEL_HEADERS_NOT_FOUND",
                    capability=CapabilityType.UPDATE_TABLE.value,
                    provider=self.provider_name,
                    document_type=self.document_type.value,
                )

            saved = self.reader.adapter.save(workbook, output_path)
            return ProviderResult.ok(
                message=f"Appended {written} row(s) to table in '{ws.title}'",
                data={
                    "sheet_name": ws.title,
                    "headers": headers,
                    "rows_appended": written,
                },
                output_path=saved,
                capability=CapabilityType.UPDATE_TABLE.value,
                provider=self.provider_name,
                document_type=self.document_type.value,
                raw={"provider": "excel"},
            )
        except Exception as e:
            return ProviderResult.fail(
                message=f"Failed to update table: {e}",
                error_code="EXCEL_UPDATE_TABLE_FAILED",
                capability=CapabilityType.UPDATE_TABLE.value,
                provider=self.provider_name,
                document_type=self.document_type.value,
            )

    def validate(self, file_path: str, **kwargs) -> ProviderResult:
        try:
            workbook = self.reader.adapter.load(file_path)
            sheet_name = self._pick(kwargs, ["sheet_name", "sheet", "sheetName"], None)
            required_cells = self._normalize_required_cells(
                self._pick(kwargs, ["required_cells", "requiredCells", "required"], [])
            )
            ws = self.reader.adapter.get_sheet(workbook, sheet_name)

            missing: list[str] = []
            for cell_ref in required_cells:
                if ws[cell_ref].value in (None, ""):
                    missing.append(cell_ref)

            return ProviderResult.ok(
                message="Excel validation completed",
                data={
                    "sheet_name": ws.title,
                    "required_cells": required_cells,
                    "missing_cells": missing,
                    "valid": len(missing) == 0,
                },
                capability=CapabilityType.VALIDATE.value,
                provider=self.provider_name,
                document_type=self.document_type.value,
                raw={"provider": "excel"},
            )
        except Exception as e:
            return ProviderResult.fail(
                message=f"Failed to validate excel document: {e}",
                error_code="EXCEL_VALIDATE_FAILED",
                capability=CapabilityType.VALIDATE.value,
                provider=self.provider_name,
                document_type=self.document_type.value,
            )

    def write(self, file_path: str, **kwargs) -> ProviderResult:
        try:
            output_path = self._safe_output_path(
                file_path,
                kwargs.get("output_path"),
                suffix="_filled",
                avoid_overwrite=bool(kwargs.get("avoid_overwrite", True)),
            )
            sheet_name = self._pick(kwargs, ["sheet_name", "sheet", "sheetName"], None)

            rows_payload = self._normalize_rows_payload(kwargs)
            cell_values = self._normalize_cell_values(
                self._pick(kwargs, ["cell_values", "cells", "updates"], {})
            )

            if self.delimited.supports(file_path):
                return self.delimited.write(
                    file_path,
                    output_path=output_path,
                    cell_values=cell_values,
                    rows_payload=rows_payload,
                )

            workbook = self.reader.adapter.load(file_path)
            ws = self.reader.adapter.get_sheet(workbook, sheet_name)

            if cell_values:
                # 写单元格场景
                for cell_ref, value in cell_values.items():
                    self.reader.adapter.write_cell(ws, cell_ref, value)
                saved = self.reader.adapter.save(workbook, output_path)
                return ProviderResult.ok(
                    message="Excel cells written successfully",
                    data={"sheet_name": ws.title, "cell_values_count": len(cell_values)},
                    output_path=saved,
                    capability=CapabilityType.WRITE.value,
                    provider=self.provider_name,
                    document_type=self.document_type.value,
                    raw={"provider": "excel"},
                )

            if rows_payload:
                start_row_value = rows_payload.get("start_row")
                start_row = int(start_row_value) if start_row_value is not None else (ws.max_row + 1 if ws.max_row else 1)
                start_col = int(rows_payload["start_col"])
                rows = rows_payload["rows"]
                saved = self.writer.write_rows(
                    file_path=file_path,
                    start_row=start_row,
                    start_col=start_col,
                    rows=rows,
                    output_path=output_path,
                    sheet_name=sheet_name,
                )
                return ProviderResult.ok(
                    message="Excel rows written successfully",
                    data={
                        "sheet_name": sheet_name or ws.title,
                        "rows_written": len(rows),
                        "start_row": start_row,
                        "start_col": start_col,
                    },
                    output_path=saved,
                    capability=CapabilityType.WRITE.value,
                    provider=self.provider_name,
                    document_type=self.document_type.value,
                    raw={"provider": "excel"},
                )

            saved = self.reader.adapter.save(workbook, output_path)
            return ProviderResult.ok(
                message="Excel document written successfully",
                data={"sheet_name": ws.title, "rows_written": 0, "cell_values_count": 0},
                output_path=saved,
                capability=CapabilityType.WRITE.value,
                provider=self.provider_name,
                document_type=self.document_type.value,
                raw={"provider": "excel"},
            )
        except Exception as e:
            return ProviderResult.fail(
                message=f"Failed to write excel document: {e}",
                error_code="EXCEL_WRITE_FAILED",
                capability=CapabilityType.WRITE.value,
                provider=self.provider_name,
                document_type=self.document_type.value,
            )

    @staticmethod
    def _pick(params: dict[str, Any], keys: list[str], default: Any = None) -> Any:
        for key in keys:
            if key in params and params.get(key) is not None:
                return params.get(key)
        return default

    @staticmethod
    def _normalize_header_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            parts = [chunk.strip() for chunk in value.replace(";", ",").split(",")]
            return [item for item in parts if item]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @staticmethod
    def _normalize_required_cells(value: Any) -> list[str]:
        return ExcelProvider._normalize_header_list(value)

    def _normalize_rows_as_records(self, rows: Any, headers: list[str]) -> list[dict[str, Any]]:
        if not rows:
            return []
        if isinstance(rows, dict):
            if isinstance(rows.get("rows"), list):
                rows = rows["rows"]
            elif isinstance(rows.get("records"), list):
                rows = rows["records"]

        result: list[dict[str, Any]] = []
        if isinstance(rows, list):
            for item in rows:
                if isinstance(item, dict):
                    result.append(dict(item))
                elif isinstance(item, (list, tuple)) and headers:
                    result.append({header: (item[idx] if idx < len(item) else None) for idx, header in enumerate(headers)})
        return result

    def _normalize_cell_values(self, payload: Any) -> dict[str, Any]:
        if payload is None:
            return {}
        if isinstance(payload, dict):
            # Nested styles: {"cell_values": {...}} / {"cells": [...]}
            for nested_key in ("cell_values", "cells", "updates"):
                nested = payload.get(nested_key)
                if nested is not None:
                    nested_map = self._normalize_cell_values(nested)
                    if nested_map:
                        return nested_map
            return {str(k): v for k, v in payload.items() if k is not None}

        result: dict[str, Any] = {}
        if isinstance(payload, (list, tuple)):
            for item in payload:
                if isinstance(item, dict):
                    cell = item.get("cell") or item.get("coordinate") or item.get("ref")
                    if cell is None:
                        continue
                    result[str(cell)] = item.get("value")
                elif isinstance(item, (list, tuple)) and len(item) == 2:
                    key, value = item
                    if key is None:
                        continue
                    result[str(key)] = value
        return result

    def _normalize_rows_payload(self, params: dict[str, Any]) -> dict[str, Any] | None:
        raw_payload = self._pick(params, ["rows_payload", "rowsPayload", "rows", "data_rows", "table_rows"], None)
        if raw_payload is None:
            return None

        if isinstance(raw_payload, dict):
            if isinstance(raw_payload.get("rows"), list):
                rows = raw_payload.get("rows") or []
            elif isinstance(raw_payload.get("records"), list):
                rows = raw_payload.get("records") or []
            else:
                rows = []
            start_row = raw_payload.get("start_row")
            if start_row is None:
                start_row = raw_payload.get("startRow")
            start_col = int(raw_payload.get("start_col") or raw_payload.get("startCol") or 1)
            headers = self._normalize_header_list(
                raw_payload.get("headers")
                or raw_payload.get("columns")
                or self._pick(params, ["headers", "header_fields", "columns"], None)
            )
            normalized_rows: list[list[Any]] = []
            for row in rows:
                if isinstance(row, (list, tuple)):
                    normalized_rows.append(list(row))
                elif isinstance(row, dict):
                    if headers:
                        normalized_rows.append([row.get(header) for header in headers])
                    else:
                        normalized_rows.append(list(row.values()))
                else:
                    normalized_rows.append([row])
            if not normalized_rows:
                return None
            normalized_start_row = None if start_row is None else max(1, int(start_row))
            return {"start_row": normalized_start_row, "start_col": max(1, start_col), "rows": normalized_rows}

        if isinstance(raw_payload, list):
            rows = [list(row) if isinstance(row, (list, tuple)) else [row] for row in raw_payload]
            if not rows:
                return None
            raw_start_row = self._pick(params, ["start_row", "startRow"], None)
            start_row = None if raw_start_row is None else int(raw_start_row)
            start_col = int(self._pick(params, ["start_col", "startCol"], 1) or 1)
            normalized_start_row = None if start_row is None else max(1, start_row)
            return {"start_row": normalized_start_row, "start_col": max(1, start_col), "rows": rows}

        return None

    def compare(self, left_file_path: str, right_file_path: str, **kwargs) -> ProviderResult:
        try:
            if self.delimited.supports(left_file_path) and self.delimited.supports(right_file_path):
                return self.delimited.compare(left_file_path, right_file_path)

            left_wb = self.reader.adapter.load(left_file_path)
            right_wb = self.reader.adapter.load(right_file_path)

            left_sheets = self.reader.adapter.list_sheets(left_wb)
            right_sheets = self.reader.adapter.list_sheets(right_wb)
            common_sheets = sorted(set(left_sheets) & set(right_sheets))

            differences: list[dict[str, Any]] = []
            for sheet in common_sheets:
                left_ws = self.reader.adapter.get_sheet(left_wb, sheet)
                right_ws = self.reader.adapter.get_sheet(right_wb, sheet)
                left_values = self.reader.adapter.read_used_range(left_ws)
                right_values = self.reader.adapter.read_used_range(right_ws)
                if left_values != right_values:
                    differences.append(
                        {
                            "sheet_name": sheet,
                            "left_rows": len(left_values),
                            "right_rows": len(right_values),
                        }
                    )

            result = {
                "left_file": left_file_path,
                "right_file": right_file_path,
                "left_sheets": left_sheets,
                "right_sheets": right_sheets,
                "common_sheets": common_sheets,
                "differences": differences,
                "identical": len(differences) == 0 and left_sheets == right_sheets,
            }
            return ProviderResult.ok(
                message="Excel documents compared successfully",
                data=result,
                capability=CapabilityType.COMPARE.value,
                provider=self.provider_name,
                document_type=self.document_type.value,
                raw={"provider": "excel"},
            )
        except Exception as e:
            return ProviderResult.fail(
                message=f"Failed to compare excel documents: {e}",
                error_code="EXCEL_COMPARE_FAILED",
                capability=CapabilityType.COMPARE.value,
                provider=self.provider_name,
                document_type=self.document_type.value,
            )

