"""Read environment settings once so every pipeline stage shares the same limits."""

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Convert environment inputs into validated database, model, and pipeline settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://rag:rag_local_only@localhost:5432/rag"
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = Field(default=1536, ge=1, le=3072)
    llm_model: str = "gpt-4.1-mini"
    chunk_size: int = Field(default=700, ge=2, le=8000)
    chunk_overlap: int = Field(default=120, ge=0)
    retrieval_top_k: int = Field(default=5, ge=1, le=20)
    max_upload_mb: int = Field(default=20, ge=1, le=100)
    max_extracted_chars: int = Field(default=2_000_000, ge=1000)
    faiss_directory: Path = Path("data/faiss")
    cors_origins: list[str] = ["http://localhost:3000"]

    @model_validator(mode="after")
    def valid_overlap(self) -> "Settings":
        """Reject non-advancing token windows before ingestion can start."""
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return self
