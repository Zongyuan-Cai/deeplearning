from __future__ import annotations

from app.document.adapters.excel_adapter import ExcelAdapter


class ExcelWriter:
    def __init__(self, adapter: ExcelAdapter | None = None) -> None:
        self.adapter = adapter or ExcelAdapter()

    def write_rows(self, file_path: str, start_row: int, start_col: int, rows: list[list], output_path: str, sheet_name: str | None = None) -> str:
        wb = self.adapter.load(file_path)
        ws = self.adapter.get_sheet(wb, sheet_name)
        self.adapter.write_rows(ws, start_row, start_col, rows)
        return self.adapter.save(wb, output_path)
