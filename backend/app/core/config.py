from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ObjectStoreProvider = Literal["s3", "tos"]


def _split_csv(value: str | list[str] | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [item.strip() for item in value if item.strip()]
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    env: str = Field(default="development", alias="ENV")
    app_name: str = Field(default="WellVision", alias="APP_NAME")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    secret_key: str = Field(alias="SECRET_KEY")
    access_token_expire_minutes: int = Field(
        default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )

    database_url: str = Field(alias="DATABASE_URL")
    auto_create_schema: bool = Field(default=False, alias="AUTO_CREATE_SCHEMA")

    object_store_provider: ObjectStoreProvider = Field(
        default="s3", alias="OBJECT_STORE_PROVIDER"
    )
    object_store_bucket: str = Field(alias="OBJECT_STORE_BUCKET")
    object_store_region: Optional[str] = Field(default=None, alias="OBJECT_STORE_REGION")

    s3_endpoint_url: Optional[str] = Field(default=None, alias="S3_ENDPOINT_URL")
    aws_access_key_id: Optional[str] = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(
        default=None, alias="AWS_SECRET_ACCESS_KEY"
    )

    tos_endpoint: Optional[str] = Field(default=None, alias="TOS_ENDPOINT")
    tos_region: Optional[str] = Field(default=None, alias="TOS_REGION")
    tos_access_key: Optional[str] = Field(default=None, alias="TOS_ACCESS_KEY")
    tos_secret_key: Optional[str] = Field(default=None, alias="TOS_SECRET_KEY")
    tos_bucket: Optional[str] = Field(default=None, alias="TOS_BUCKET")

    raw_prefix: str = Field(default="raw/", alias="RAW_PREFIX")
    clean_prefix: str = Field(default="clean/", alias="CLEAN_PREFIX")
    feature_prefix: str = Field(default="feature/", alias="FEATURE_PREFIX")
    serve_prefix: str = Field(default="serve/", alias="SERVE_PREFIX")

    redis_url: str = Field(alias="REDIS_URL")
    celery_broker_url: Optional[str] = Field(default=None, alias="CELERY_BROKER_URL")
    celery_result_backend: Optional[str] = Field(
        default=None, alias="CELERY_RESULT_BACKEND"
    )

    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    frontend_origin: Optional[str] = Field(default=None, alias="FRONTEND_ORIGIN")
    cors_allow_origins_raw: list[str] | str | None = Field(
        default=None, alias="CORS_ALLOW_ORIGINS"
    )

    bootstrap_tenant_name: str = Field(
        default="Default Tenant", alias="BOOTSTRAP_TENANT_NAME"
    )
    bootstrap_admin_email: str = Field(
        default="admin@wellvision.io", alias="BOOTSTRAP_ADMIN_EMAIL"
    )
    bootstrap_admin_password: str = Field(
        default="ChangeMe123!", alias="BOOTSTRAP_ADMIN_PASSWORD"
    )

    max_upload_mb: int = Field(default=2048, alias="MAX_UPLOAD_MB")
    multipart_part_size_mb: int = Field(default=16, alias="MULTIPART_PART_SIZE_MB")
    multipart_presign_expires_seconds: int = Field(default=3600, alias="MULTIPART_PRESIGN_EXPIRES_SECONDS")
    parquet_preview_max_mb: int = Field(default=256, alias="PARQUET_PREVIEW_MAX_MB")
    import_worker_enabled: bool = Field(default=True, alias="IMPORT_WORKER_ENABLED")
    import_worker_poll_seconds: int = Field(default=5, alias="IMPORT_WORKER_POLL_SECONDS")
    import_worker_concurrency: int = Field(default=2, alias="IMPORT_WORKER_CONCURRENCY")
    import_batch_size: int = Field(default=2000, alias="IMPORT_BATCH_SIZE")
    import_preview_bytes: int = Field(default=2 * 1024 * 1024, alias="IMPORT_PREVIEW_BYTES")

    timescaledb_enabled: bool = Field(default=False, alias="TIMESCALEDB_ENABLED")
    timescaledb_chunk_interval_hours: int = Field(default=24, alias="TIMESCALEDB_CHUNK_INTERVAL_HOURS")
    timescaledb_compress_after_hours: int = Field(default=0, alias="TIMESCALEDB_COMPRESS_AFTER_HOURS")
    timescaledb_retention_days: int = Field(default=0, alias="TIMESCALEDB_RETENTION_DAYS")

    @property
    def cors_allow_origins(self) -> list[str]:
        return _split_csv(self.cors_allow_origins_raw)

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        if not value or "REPLACE_WITH" in value or value == "CHANGE_ME":
            raise ValueError("SECRET_KEY must be set to a secure random string.")
        if len(value) < 16:
            raise ValueError("SECRET_KEY must be at least 16 characters long.")
        return value

    @field_validator("object_store_bucket")
    @classmethod
    def validate_bucket(cls, value: str) -> str:
        if not value:
            raise ValueError("OBJECT_STORE_BUCKET is required.")
        return value

    @field_validator("object_store_region")
    @classmethod
    def validate_region(cls, value: Optional[str]) -> Optional[str]:
        return value or None

    @field_validator("multipart_part_size_mb")
    @classmethod
    def validate_multipart_part_size_mb(cls, value: int) -> int:
        if value < 5:
            raise ValueError("MULTIPART_PART_SIZE_MB must be >= 5 for S3-compatible multipart upload.")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
