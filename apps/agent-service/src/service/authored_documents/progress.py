"""Progress reporting seam between the draft pipeline and whoever streams it.

The service only announces phases; the caller decides how (or whether) they
reach the user, so the use-case layer stays free of streaming frameworks.
"""

from __future__ import annotations

from typing import Protocol

from core.types.authored_documents import BlockChange, GenerationPhase


class ProgressSink(Protocol):
    def phase(
        self,
        phase: GenerationPhase,
        *,
        applied: int | None = None,
        total: int | None = None,
        changes: tuple[BlockChange, ...] = (),
    ) -> None: ...


class _NullProgress:
    """Discards every phase; the default for callers that stream nothing."""

    def phase(self, *_args: object, **_kwargs: object) -> None:
        return None


NULL_PROGRESS: ProgressSink = _NullProgress()
