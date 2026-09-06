"""Application port for final LIVE-session integrity admission."""

from __future__ import annotations

from typing import Protocol

from ..domain.enterprise.models.discovery import LiveSessionSafetyEvidence


class LiveSessionSafety(Protocol):
    """Finalize outer runtime/file health before evidence is persisted."""

    def finalize(self) -> LiveSessionSafetyEvidence: ...
