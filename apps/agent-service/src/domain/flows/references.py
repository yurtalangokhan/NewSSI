"""Outgoing flow references in a spec — the edges of the *reference* graph.

Deliberately separate from ``validator.py``. The validator answers "is this
one flow well formed"; this answers "which other flows does it run", which is
what publish-time cycle detection needs.

Kept as its own module because tool mode will add a second source of
references (an agent wired to a flow-backed tool). On that day this function
gains one branch and the cycle detector does not change at all — which is the
whole reason it is not just a loop inside the detector.

Pure and total, like ``handles.py`` and ``handle_types.py``: no I/O, one
answer per input, never raises. A hand-edited spec is untrusted input, not a
crash.
"""

from __future__ import annotations

from models.flows import FlowSpec

_RUN_FLOW = "RunFlow"


def flow_references(spec: FlowSpec) -> set[str]:
    """The definition ids ``spec`` runs as sub-flows.

    A blank target is deliberately *not* a reference: an unconfigured node is
    reported by ``FLOW_RUNFLOW_MISSING_TARGET``, and treating ``""`` as an
    edge would turn one clear error into a confusing cycle report.
    """
    refs: set[str] = set()
    for node in spec.nodes:
        if node.type != _RUN_FLOW:
            continue
        raw = node.values.get("flow_id")
        target = "" if raw is None else str(raw).strip()
        if target:
            refs.add(target)
    return refs
