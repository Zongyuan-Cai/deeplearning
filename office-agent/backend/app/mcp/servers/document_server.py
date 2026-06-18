from __future__ import annotations

from app.document.service import DocumentService


class DocumentServer:
    def __init__(self) -> None:
        self.document_service = DocumentService()

    def summarize_document(
        self,
        file_path: str | None = None,
        file_paths: list[str] | None = None,
        filename: str | None = None,
        **kwargs,
    ):
        return self.document_service.summarize_document(
            file_path=file_path,
            file_paths=file_paths,
            filename=filename,
            **kwargs,
        )

    def read_document(self, file_path: str, filename: str | None = None, **kwargs):
        return self.document_service.read_document(file_path=file_path, filename=filename, **kwargs)

    def extract_structured_data(self, file_path: str, filename: str | None = None, **kwargs):
        return self.document_service.extract_fields(file_path=file_path, filename=filename, **kwargs)

    def fill_fields(self, file_path: str, filename: str | None = None, **kwargs):
        return self.document_service.fill_document(file_path=file_path, filename=filename, **kwargs)

    def update_table(self, file_path: str, filename: str | None = None, **kwargs):
        return self.document_service.update_table(file_path=file_path, filename=filename, **kwargs)

    def validate_document(self, file_path: str, filename: str | None = None, **kwargs):
        return self.document_service.validate_document(file_path=file_path, filename=filename, **kwargs)

    def scan_template_fields(self, file_path: str, filename: str | None = None, **kwargs):
        return self.document_service.scan_template(file_path=file_path, filename=filename, **kwargs)
