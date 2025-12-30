from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HealthStatus:
    status: str


def get_health() -> HealthStatus:
    # Keep services pure-ish and testable.
    return HealthStatus(status="ok")
