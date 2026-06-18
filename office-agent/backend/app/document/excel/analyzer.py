from __future__ import annotations

from app.document.adapters.excel_adapter import ExcelAdapter


class ExcelAnalyzer:
    def __init__(self, adapter: ExcelAdapter | None = None) -> None:
        self.adapter = adapter or ExcelAdapter()

    def extract_table_by_header(self, file_path: str, headers: list[str], sheet_name: str | None = None):
        wb = self.adapter.load(file_path)
        ws = self.adapter.get_sheet(wb, sheet_name)
        return self.adapter.extract_table_by_header(ws, headers)
