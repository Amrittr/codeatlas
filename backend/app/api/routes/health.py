from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request

from app import __version__
from app.analyzers.exclusions import DEFAULT_EXCLUSION_RULES, MAX_PATTERN_LENGTH, MAX_PATTERNS, REASON_LABELS
from app.schemas.project import CamelModel

router = APIRouter(prefix="/api", tags=["system"])


class HealthResponse(CamelModel):
    status: Literal["ok"] = "ok"
    version: str


class Limits(CamelModel):
    max_upload_bytes: int
    max_uncompressed_bytes: int
    max_file_bytes: int
    max_files: int
    max_depth: int


class ExclusionRule(CamelModel):
    name: str
    reason: str
    label: str


class PatternLimits(CamelModel):
    max_patterns: int = MAX_PATTERNS
    max_pattern_length: int = MAX_PATTERN_LENGTH


class ConfigResponse(CamelModel):
    processing_mode: Literal["server"] = "server"
    project_ttl_seconds: int
    limits: Limits
    default_exclusions: list[ExclusionRule]
    pattern_limits: PatternLimits = PatternLimits()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(version=__version__)


@router.get("/config", response_model=ConfigResponse)
def public_config(request: Request) -> ConfigResponse:
    settings = request.app.state.settings
    return ConfigResponse(
        project_ttl_seconds=settings.project_ttl_seconds,
        limits=Limits(
            max_upload_bytes=settings.max_upload_bytes,
            max_uncompressed_bytes=settings.max_uncompressed_bytes,
            max_file_bytes=settings.max_file_bytes,
            max_files=settings.max_files,
            max_depth=settings.max_depth,
        ),
        default_exclusions=[
            ExclusionRule(name=name, reason=reason, label=REASON_LABELS[reason])
            for name, reason in DEFAULT_EXCLUSION_RULES.items()
        ],
    )
