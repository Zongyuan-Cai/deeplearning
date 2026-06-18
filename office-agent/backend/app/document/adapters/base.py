from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseDocumentAdapter(ABC):
    @abstractmethod
    def load(self, file_path: str) -> Any:
        raise NotImplementedError

    @abstractmethod
    def save(self, document: Any, output_path: str) -> str:
        raise NotImplementedError