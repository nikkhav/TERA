from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    database_url: str = "postgresql+psycopg://tera:tera-local@localhost:5433/tera"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "tera-local"
    s3_secret_key: str = "tera-local-secret"
    s3_bucket: str = "tera-documents"
    s3_region: str = "us-east-1"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:9b"
    ollama_think: bool | None = None
    model_context_tokens: int = Field(default=8192, ge=4096)
    model_output_tokens: int = Field(default=1536, ge=256)
    model_timeout_seconds: int = Field(default=300, ge=1, le=900)
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1)
    max_pdf_pages: int = Field(default=200, ge=1)
    max_text_characters: int = Field(default=2_000_000, ge=1)
    worker_poll_seconds: float = Field(default=2, gt=0)
    job_lease_seconds: int = Field(default=1200, ge=60)

    @model_validator(mode="after")
    def validate_budgets(self):
        if self.model_context_tokens - self.model_output_tokens < 3072:
            raise ValueError("Reserve at least 3072 tokens for instructions and PDF text")
        if self.job_lease_seconds <= self.model_timeout_seconds + 60:
            raise ValueError("Job lease must exceed model timeout by more than 60 seconds")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
