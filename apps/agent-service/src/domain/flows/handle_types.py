"""Handle type compatibility.

Pure and total: every pair of ``PortType`` values returns a boolean, never
raises. Coercions are deliberately asymmetric — see
``.tmp/flow-canvas-design.md`` section 4.7. Silent coercion is how visual
builders produce flows that validate and then behave unexpectedly at runtime.

Adding a new ``PortType`` needs no change here to stay total (identity and the
``Data`` rules cover it automatically); it only needs an entry in
``_EXPLICIT_COMPATIBLE`` if it should deliberately coerce into something else.
That is a product decision each time, not a default.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from models.flows import PortType

_EXPLICIT_COMPATIBLE: Final[frozenset[tuple[PortType, PortType]]] = frozenset(
    {
        (PortType.MESSAGE, PortType.TEXT),
    }
)


def is_compatible(source: PortType, target: PortType) -> bool:
    """Whether a value of type ``source`` may flow into a ``target`` port.

    ``Trigger`` isolation takes priority over the ``Data`` catch-all: a
    Trigger is a pure signal with no payload, so it does not satisfy a Data
    port just because Data otherwise accepts anything.
    """
    if source == target:
        return True
    if source is PortType.TRIGGER or target is PortType.TRIGGER:
        return False
    if target is PortType.DATA:
        return True
    if source is PortType.DATA:
        return False
    return (source, target) in _EXPLICIT_COMPATIBLE


def handles_compatible(source_types: Sequence[PortType], target_types: Sequence[PortType]) -> bool:
    """Whether any type on the source handle may flow into any type on the target."""
    return any(is_compatible(s, t) for s in source_types for t in target_types)
