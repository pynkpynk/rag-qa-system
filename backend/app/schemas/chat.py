"""Chat request schema for backwards compatibility."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class ChatAskRequest(BaseModel):
    """Minimal request schema used by legacy tests and tooling."""

    question: str | None = Field(default=None)
    message: str | None = Field(default=None)
    run_id: str | None = Field(default=None)
    document_ids: list[str] | None = Field(default=None)
    debug: bool = False
    mode: str | None = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def _copy_message_if_needed(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        question = data.get("question")
        message = data.get("message")
        if (not isinstance(question, str) or not question.strip()) and isinstance(message, str) and message.strip():
            data["question"] = message
        return data

    @model_validator(mode="after")
    def _normalize(self) -> "ChatAskRequest":
        question = (self.question or "").strip()
        if not question:
            raise ValueError("question or message must be provided")
        self.question = question

        if self.message is not None:
            msg = self.message.strip()
            self.message = msg if msg else None

        if self.run_id is not None:
            rid = self.run_id.strip()
            if not rid:
                raise ValueError("run_id must not be empty if provided")
            self.run_id = rid

        docs = []
        for raw in self.document_ids or []:
            doc_id = (raw or "").strip()
            if doc_id:
                docs.append(doc_id)
        self.document_ids = docs or None

        if self.run_id and self.document_ids:
            raise ValueError("Provide either run_id or document_ids, not both.")

        if self.mode is not None:
            mode = self.mode.strip()
            self.mode = mode if mode else None

        return self

    def effective_query(self) -> str:
        """Return the primary query string used by tests."""
        if self.question:
            q = self.question.strip()
            if q:
                return q
        if self.message:
            msg = self.message.strip()
            if msg:
                return msg
        return ""
