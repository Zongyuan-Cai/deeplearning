from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExcelTable:
    sheet_name: str
    headers: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
