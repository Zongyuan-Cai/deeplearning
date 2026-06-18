from __future__ import annotations

from app.document.adapters.excel_adapter import ExcelAdapter


class ExcelReader:
    def __init__(self, adapter: ExcelAdapter | None = None) -> None:
        self.adapter = adapter or ExcelAdapter()

    def read_used_range(self, file_path: str, sheet_name: str | None = None):
        wb = self.adapter.load(file_path)
        ws = self.adapter.get_sheet(wb, sheet_name)
        return self.adapter.read_used_range(ws)
