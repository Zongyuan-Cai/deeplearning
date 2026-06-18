from __future__ import annotations

from typing import Any

from app.document.shared.mapping import map_record_to_fields


class ExcelMapper:
    def map_rows(self, rows: list[dict[str, Any]], target_fields: list[str]) -> list[dict[str, Any]]:
        return [map_record_to_fields(row, target_fields) for row in rows]
