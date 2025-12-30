from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: dict


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
