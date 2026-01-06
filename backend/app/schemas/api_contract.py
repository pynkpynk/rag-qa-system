from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    app: str
    version: str
    status: Literal["ok", "degraded", "error"] | str = Field(
        ..., description="Overall health status"
    )
    time_utc: str
    app_env: str
    auth_mode: str
    git_sha: str
    llm_enabled: bool
    openai_offline: bool
    openai_key_present: bool


class DocumentListItem(BaseModel):
    document_id: str
    filename: str
    status: str
    error: str | None = None


class DocumentDetailResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    error: str | None = None
    content_hash: str | None = None
    storage_key: str | None = None
    meta: dict[str, Any] | None = None
    created_at: str


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    dedup: bool = False


class DocumentPageChunkItem(BaseModel):
    chunk_id: str
    chunk_index: int
    text: str


class DocumentReindexResponse(BaseModel):
    document_id: str
    queued: bool
    reason: str | None = None


class ChunkResponse(BaseModel):
    chunk_id: str
    document_id: str
    filename: str | None
    page: int | None
    chunk_index: int
    text: str


class ChunkDBStatus(BaseModel):
    dialect: str | None = None
    alembic_revision: str | None = None
    chunks_fts_column: bool | None = None
    fts_gin_index: bool | None = None
    pg_trgm_installed: bool | None = None
    text_trgm_index: bool | None = None


class ChunkHealthResponse(BaseModel):
    ok: bool
    principal_sub: str | None = None
    db: ChunkDBStatus | None = None


class ChatCitation(BaseModel):
    source_id: str | None = None
    page: int | None = None
    filename: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    chunk_id_missing_reason: str | None = None
    drilldown_blocked_reason: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[ChatCitation]
    run_id: str | None = None
    request_id: str
    retrieval_debug: dict[str, Any] | None = None
    debug_meta: dict[str, Any] | None = None


class ChatAskResponse(ChatResponse):
    pass


class RunListItem(BaseModel):
    run_id: str
    created_at: str
    status: str
    document_ids: list[str]


class RunDetailResponse(BaseModel):
    run_id: str
    created_at: str
    config: dict[str, Any]
    status: str
    error: str | None
    document_ids: list[str]


class RunDeleteResponse(BaseModel):
    deleted: bool
    run_id: str


class RunCleanupSkippedItem(BaseModel):
    run_id: str
    status: str | None = None
    created_at: str | None = None


class RunCleanupResponse(BaseModel):
    dry_run: bool
    older_than_days: int
    cutoff_utc: str
    limit: int | None = None
    candidates: list[RunListItem] | None = None
    skipped: list[RunCleanupSkippedItem]
    count: int | None = None
    deleted_count: int | None = None
    deleted_run_ids: list[str] | None = None


class DebugAwsWhoAmIIdentity(BaseModel):
    account: str | None = None
    arn: str | None = None
    user_id: str | None = None


class DebugAwsWhoAmIResponse(BaseModel):
    region: str
    bucket: str | None = None
    access_key_prefix: str | None = None
    caller_identity: DebugAwsWhoAmIIdentity


class DebugS3HeadResponse(BaseModel):
    bucket: str
    region: str
    key: str
    etag: str | None = None
    content_length: Optional[int] = Field(default=None, repr=False)
    content_type: str | None = None
    last_modified: str | None = None
    server_side_encryption: str | None = None


__all__ = [
    "ChatCitation",
    "ChatAskResponse",
    "ChatResponse",
    "ChunkHealthResponse",
    "ChunkResponse",
    "DebugAwsWhoAmIResponse",
    "DebugAwsWhoAmIIdentity",
    "DebugS3HeadResponse",
    "DocumentDetailResponse",
    "DocumentListItem",
    "DocumentPageChunkItem",
    "DocumentReindexResponse",
    "DocumentUploadResponse",
    "HealthResponse",
    "RunCleanupResponse",
    "RunCleanupSkippedItem",
    "RunDeleteResponse",
    "RunDetailResponse",
    "RunListItem",
]
