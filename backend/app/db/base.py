from __future__ import annotations

from sqlalchemy.orm import declarative_base

# Single canonical declarative base for all ORM models.
Base = declarative_base()

__all__ = ["Base"]
