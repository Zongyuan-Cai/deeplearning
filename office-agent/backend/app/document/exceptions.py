class DocumentError(Exception):
    """文档子系统统一基类异常。"""


class DocumentServiceError(DocumentError):
    """service / router 层通用异常。"""


class UnsupportedDocumentType(DocumentServiceError):
    """不支持的文档类型。"""


class CapabilityNotSupported(DocumentServiceError):
    """文档类型不支持该 capability。"""


class DocumentProviderError(DocumentServiceError):
    """provider 调用失败的统一包装异常。"""


class DocumentReadError(DocumentProviderError):
    """文档读取失败。"""


class DocumentLocateError(DocumentProviderError):
    """文档定位失败。"""


class DocumentFillError(DocumentProviderError):
    """文档填充失败。"""


class DocumentValidationError(DocumentProviderError):
    """文档校验失败。"""


class DocumentWriteError(DocumentProviderError):
    """文档写出失败。"""


# ===== 向后兼容旧命名 =====
UnsupportedDocumentTypeError = UnsupportedDocumentType
UnsupportedCapabilityError = CapabilityNotSupported
DocumentVerifyError = DocumentValidationError
