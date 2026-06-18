from abc import ABC, abstractmethod
from typing import Any, Dict, List

from app.document.models import ParsedDocument, VerificationResult


class BaseDocumentReader(ABC):
    @abstractmethod
    def read(self, file_path: str) -> ParsedDocument:
        raise NotImplementedError


class BaseTemplateInspector(ABC):
    @abstractmethod
    def extract_placeholders(self, file_path: str) -> List[str]:
        raise NotImplementedError


class BaseDocumentWriter(ABC):
    @abstractmethod
    def fill_template(self, template_path: str, data: Dict[str, Any]) -> str:
        raise NotImplementedError


class BaseDocumentVerifier(ABC):
    @abstractmethod
    def verify_filled_document(
        self,
        output_path: str,
        expected_placeholders: List[str],
        filled_data: Dict[str, Any],
    ) -> VerificationResult:
        raise NotImplementedError