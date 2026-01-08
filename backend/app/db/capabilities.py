from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable, List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass
class DBCapabilities:
    extensions_present: List[str] = field(default_factory=list)
    pg_trgm_available: bool = False
    vector_available: bool = False
    checked_ok: bool = False
    error: Optional[str] = None
    missing_required_extensions: List[str] = field(default_factory=list)


_CURRENT_DB_CAPS: DBCapabilities | None = None


def _clean_required(exts: Sequence[str] | None) -> List[str]:
    if not exts:
        return []
    cleaned = sorted({(ext or "").strip().lower() for ext in exts if (ext or "").strip()})
    return cleaned


def detect_db_capabilities(
    engine: Engine | None, required_extensions: Sequence[str] | None = None
) -> DBCapabilities:
    required = _clean_required(required_extensions)
    if engine is None:
        return DBCapabilities(
            extensions_present=[],
            checked_ok=False,
            error="engine unavailable",
            missing_required_extensions=required,
        )
    backend = (engine.url.get_backend_name() or "").lower()
    if not backend.startswith("postgresql"):
        return DBCapabilities(
            extensions_present=[],
            checked_ok=False,
            error=f"unsupported dialect {backend}",
            missing_required_extensions=required,
        )
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT extname FROM pg_extension")).scalars().all()
    except Exception as exc:  # pragma: no cover - depends on env
        return DBCapabilities(
            extensions_present=[],
            checked_ok=False,
            error=str(exc),
            missing_required_extensions=required,
        )
    normalized = sorted({(row or "").lower() for row in rows if row})
    missing = [ext for ext in required if ext not in normalized]
    return DBCapabilities(
        extensions_present=normalized,
        pg_trgm_available="pg_trgm" in normalized,
        vector_available="vector" in normalized,
        checked_ok=True,
        error=None,
        missing_required_extensions=missing,
    )


def set_current_db_capabilities(caps: DBCapabilities | None) -> None:
    global _CURRENT_DB_CAPS
    _CURRENT_DB_CAPS = caps


def get_current_db_capabilities() -> DBCapabilities | None:
    return _CURRENT_DB_CAPS


def db_caps_to_dict(caps: DBCapabilities | None):
    if caps is None:
        return None
    return asdict(caps)
