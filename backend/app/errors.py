"""Expose safe, actionable pipeline failures without leaking provider or database internals."""


class PipelineError(Exception):
    """Carry a public message and HTTP status from a service to the API boundary."""

    status_code = 400
    code = "pipeline_error"


class InvalidUpload(PipelineError):
    """Signal a bad extension, MIME type, file contents, or empty extraction."""

    code = "invalid_upload"


class UploadTooLarge(PipelineError):
    """Stop ingestion when the configured byte or extracted-text budget is exceeded."""

    status_code = 413
    code = "upload_too_large"


class ProviderError(PipelineError):
    """Turn missing credentials or failed embedding/LLM requests into a safe error."""

    status_code = 503
    code = "provider_unavailable"


class StorageError(PipelineError):
    """Report a FAISS consistency or persistence problem without serving invalid results."""

    status_code = 503
    code = "storage_unavailable"


class DocumentNotFound(PipelineError):
    """Reject unknown document selections before semantic retrieval or deletion."""

    status_code = 404
    code = "document_not_found"
