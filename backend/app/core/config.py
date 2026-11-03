"""Application settings. Every environment variable is read here and nowhere else."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MB = 1024 * 1024
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FRONTEND_DIR = REPO_ROOT / "frontend" / "public"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CODEATLAS_",
        env_file=REPO_ROOT / ".env",
        extra="ignore",
    )

    environment: str = "development"

    # Archive safety limits. Enforced while extracting, not only up front. Defaults come from
    # benchmarks in docs/TESTING.md (100k files: ~18 s, ~290 MB peak RSS on an Apple M4).
    max_upload_bytes: int = Field(100 * MB, gt=0)
    max_uncompressed_bytes: int = Field(1024 * MB, gt=0)
    max_file_bytes: int = Field(50 * MB, gt=0)
    max_files: int = Field(100_000, gt=0)
    max_directories: int = Field(50_000, gt=0)
    max_archive_entries: int = Field(200_000, gt=0)
    max_depth: int = Field(64, gt=0)
    max_path_length: int = Field(1024, gt=0)
    max_compression_ratio: float = Field(100.0, gt=1)
    compression_ratio_floor_bytes: int = Field(10 * MB, ge=0)
    max_analysis_seconds: float = Field(300.0, gt=0)
    max_concurrent_analyses: int = Field(2, gt=0)
    max_queued_jobs: int = Field(4, ge=0)
    job_ttl_seconds: int = Field(600, gt=0)
    max_tree_response_nodes: int = Field(25_000, gt=0)
    # Source parsing for the architecture map (~480 real files/s per core, measured). Past this budget
    # the remaining files are left unparsed and the map is marked partial instead of failing.
    max_parse_seconds: float = Field(150.0, gt=0)
    # Parsing runs in a child process; a file slower than this (hostile input) is killed and skipped.
    max_parse_file_seconds: float = Field(5.0, gt=0)

    # In-memory result retention.
    project_ttl_seconds: int = Field(1800, gt=0)
    max_stored_projects: int = Field(10, gt=0)
    max_stored_nodes: int = Field(500_000, gt=0)

    temp_dir: Path | None = None

    serve_frontend: bool = True
    frontend_dir: Path = DEFAULT_FRONTEND_DIR
    cors_origins: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
