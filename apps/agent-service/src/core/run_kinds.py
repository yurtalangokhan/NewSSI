"""The execution namespace of a conversation thread.

``production`` threads are real end-user conversations; ``playground`` threads
are throwaway flow-canvas test runs, swept by
:class:`service.PlaygroundRetentionService.PlaygroundRetentionWorker`.

:class:`enum.StrEnum`, so ``RunKind.PLAYGROUND == "playground"`` and it stores /
serializes exactly as before.
"""

from __future__ import annotations

from enum import StrEnum


class RunKind(StrEnum):
    PRODUCTION = "production"
    PLAYGROUND = "playground"


# The column default and the default filter for "show me my conversations".
DEFAULT_RUN_KIND = RunKind.PRODUCTION
