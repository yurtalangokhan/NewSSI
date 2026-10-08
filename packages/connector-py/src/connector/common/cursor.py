"""Incremental cursors: one comparator and one tracker for every source.

A source that supports incremental sync has to do three things per stream: find
out where the last run stopped, notice how far this run got, and say so in a
``State``. :class:`CursorTracker` does the bookkeeping; the source decides what
the cursor value of a record is.

Two kinds of streams exist:

* **Ordered** - the source returns rows sorted by the cursor (``ORDER BY cursor``).
  The last value read is the new cursor, in the source's own sort order, and
  the tracker can checkpoint *while* the stream is read: once the value
  changes, every row carrying the previous value has been delivered.
* **Unordered** - records arrive in any order (most APIs). The cursor is the
  latest value seen, compared with :func:`is_newer`, and is only known at the
  end of the stream.

The stored state is ``{"cursor": value}`` in both cases.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from ..models import ConfiguredStream, State, SyncMode, SyncState, utcnow
from .rest_source import parse_iso


def incremental_cursor(configured: ConfiguredStream) -> str | None:
    """The cursor field to use, or ``None`` when the stream is not synced incrementally."""
    if configured.sync_mode is not SyncMode.INCREMENTAL or not configured.cursor_field:
        return None
    return configured.cursor_field[0]


def _order_key(value: Any) -> tuple[int, Any]:
    """Comparable key for cursor values of mixed origin (ISO strings, epochs, ids).

    Integers stay integers: as floats, 64-bit ids above 2**53 are no longer told
    apart, and a cursor that stops short of the last id read loses rows.
    """
    if isinstance(value, bool):
        return (0, int(value))
    if isinstance(value, int | float):
        return (0, value)
    parsed = parse_iso(value)
    if parsed is not None:
        return (1, parsed.timestamp())
    text = str(value)
    if re.fullmatch(r"-?\d+", text):
        return (0, int(text))
    if re.fullmatch(r"-?\d+\.\d+", text):
        return (0, float(text))
    return (2, text)


def is_newer(value: Any, than: Any) -> bool:
    if value is None:
        return False
    if than is None:
        return True
    a, b = _order_key(value), _order_key(than)
    return a > b if a[0] == b[0] else str(value) > str(than)


def later(current: Any, candidate: Any) -> Any:
    """Return whichever cursor value is later; ISO timestamps are normalised to UTC."""
    if candidate is None:
        return current
    parsed = parse_iso(candidate)
    normalised = parsed.isoformat() if parsed is not None else candidate
    return normalised if is_newer(normalised, current) else current


CURSOR_SKEW_SECONDS = 300
"""How far behind the start of a read an unordered timestamp cursor is held (see
:func:`held_back`)."""


def held_back(value: Any, floor: Any, started: datetime) -> Any:
    """``value`` capped at ``started`` minus :data:`CURSOR_SKEW_SECONDS`, never below ``floor``.

    An unordered stream is read in parts (mailboxes, projects, pages of an API that
    does not sort): a record written to an earlier part while a later one is read
    carries a stamp below the final cursor and would never be read. A source clock
    ahead of ours has the same effect. Holding the cursor back to the start of the
    read, less a margin for skew, makes the next run read such records; what it
    reads twice, record keys absorb. Only timestamps are held back; ``floor`` (the
    saved cursor) is never undercut.
    """
    parsed = parse_iso(value)
    if parsed is None:
        return value
    limit = started - timedelta(seconds=CURSOR_SKEW_SECONDS)
    if parsed <= limit:
        return value
    capped = limit.isoformat()
    return capped if floor is None or is_newer(capped, floor) else floor


class CursorTracker:
    """Incremental bookkeeping of one stream.

    Disabled (``enabled=False``, a full refresh) it remembers nothing and emits
    nothing, so a source can use it without branching on the sync mode.

    ``checkpoint_every`` (ordered streams only) emits a ``State`` from
    :meth:`observe` about every that many records, so a run that dies in the
    middle of a large stream resumes near where it stopped instead of at the
    start of the stream.
    """

    def __init__(
        self,
        stream: str,
        state: SyncState | None = None,
        *,
        enabled: bool = True,
        ordered: bool = False,
        checkpoint_every: int | None = None,
    ) -> None:
        self.stream = stream
        self.enabled = enabled
        self.ordered = ordered
        self.started = utcnow()
        """When this read began; an unordered cursor is held back to it (``held_back``)."""
        saved = state.get(stream).get("cursor") if (enabled and state is not None) else None
        self.start: Any = saved
        """Where the previous run stopped; ``None`` on a first or full run."""
        self.value: Any = saved
        self._checkpoint_every = checkpoint_every if ordered else None
        self._complete: Any = None  # latest value whose rows have all been delivered
        self._boundary_ok = False  # may the current value serve as a checkpoint boundary?
        self._emitted: Any = saved
        self._since_checkpoint = 0

    def observe(self, value: Any, *, exact: bool = True) -> State | None:
        """Take note of the cursor value of the record about to be emitted.

        Returns a checkpoint to yield *before* that record, or ``None``.

        ``exact=False`` says equality of this value is not what the source sorts
        by (text under a case-insensitive collation, say). Such a value moves the
        cursor but is never used as a mid-stream checkpoint.
        """
        if not self.enabled or value is None:
            return None
        if not self.ordered:
            self.value = later(self.value, value)
            return None

        if value != self.value:
            if self._boundary_ok:
                self._complete = self.value
            self.value = value
        self._boundary_ok = exact
        self._since_checkpoint += 1
        if (
            self._checkpoint_every is not None
            and self._since_checkpoint >= self._checkpoint_every
            and self._complete is not None
            and self._complete != self._emitted
        ):
            self._since_checkpoint = 0
            self._emitted = self._complete
            return State(stream=self.stream, data={"cursor": self._complete})
        return None

    def final_state(self) -> State | None:
        """The checkpoint to yield once the stream has been read to its end."""
        if not self.enabled or self.value is None:
            return None
        value = self.value if self.ordered else held_back(self.value, self.start, self.started)
        return State(stream=self.stream, data={"cursor": value})


class ReadAtCursor:
    """Which files a run read at the cursor's own timestamp.

    File listings carry coarse modification times (whole seconds on S3 and most
    servers). A file written in the same second as the last one read, after the
    listing was taken, carries the cursor's timestamp: skipping everything up to
    the cursor would lose it for good, reading everything from the cursor on would
    read the last files again on every run. So the state also names the files
    read at the cursor timestamp (``keys_at_cursor``), and the next run skips
    exactly those. A state without the list (written before it existed) is
    treated as it was: the cursor second is skipped.

    Wraps an ordered :class:`CursorTracker`; call :meth:`due` before reading a
    file, :meth:`note` once it is read, :meth:`attach` on every ``State`` yielded.
    """

    STATE_KEY = "keys_at_cursor"

    def __init__(self, tracker: CursorTracker, saved: Mapping[str, Any] | None) -> None:
        self.last: datetime | None = parse_iso(tracker.start) if tracker.enabled else None
        known = (saved or {}).get(self.STATE_KEY)
        self._skip_cursor_second = self.last is not None and known is None
        self._keys: dict[str, list[str]] = {}
        if self.last is not None and known is not None:
            self._keys[self.last.isoformat()] = [str(k) for k in known]

    def due(self, modified: datetime | None, key: str) -> bool:
        """Is the file ``key`` modified at ``modified`` to be read in this run?"""
        if self.last is None or modified is None or modified > self.last:
            return True
        if modified < self.last or self._skip_cursor_second:
            return False
        return key not in self._keys.get(self.last.isoformat(), ())

    def note(self, stamp: str, key: str) -> None:
        """Record ``key`` as read at ``stamp`` (ISO). Files arrive oldest first, and a
        checkpoint names at most the previous stamp, so two stamps' keys suffice."""
        self._keys.setdefault(_utc_iso(stamp), []).append(key)
        while len(self._keys) > 2:
            del self._keys[next(iter(self._keys))]

    def attach(self, state: State) -> State:
        cursor = state.data.get("cursor")
        keys = self._keys.get(_utc_iso(cursor), []) if cursor is not None else []
        state.data[self.STATE_KEY] = list(keys)
        return state


def _utc_iso(stamp: Any) -> str:
    parsed = parse_iso(stamp)
    return parsed.isoformat() if parsed is not None else str(stamp)
