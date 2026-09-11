"""Human labels for FlowAgent canvas nodes in the live SSE timeline.

The client (GraphStageStrip) keeps its own CANONICAL_COMPONENT_MAP; this is
the server-side equivalent used only to fill ``flow_stage_start.label``,
which the client trusts. The client map stays as a fallback, not the source
of truth. Canvas node ids ("ReActAgent-f296f72f") are never shown raw.
"""

from __future__ import annotations

import re
from typing import Any

_PRETTY: dict[str, str] = {
    "ReActAgent": "ReAct Agent",
    "ResearchAgent": "Research Agent",
    "SelfReflectAgent": "Self-Reflect Agent",
    "ZeroShotAgent": "Zero-Shot Agent",
    "PipelineStage": "Pipeline Stage",
    "Supervisor": "Supervisor",
    "ConditionalRouter": "If-Else",
    "ChatOutput": "Chat Output",
    "ChatInput": "Chat Input",
}


def _prettify(node_type: str) -> str:
    if node_type in _PRETTY:
        return _PRETTY[node_type]
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", node_type)


# A canvas rename lands under ``label`` whatever the node type is, so this key
# is always a stage name.
_RENAME_VALUE_KEYS = ("label",)
# ``name`` / ``stage_name`` / ``display_name`` only mean "stage name" on the
# types that actually declare such a field. This must stay a per-type opt-in:
# ``SetVariable.name`` is a *variable* name (Phase 0) and labelling the stage
# with it showed a raw scratch key ("musteri_mesaji") where the component name
# belongs.
_STAGE_NAME_VALUE_KEYS = ("name", "stage_name", "display_name")
_TYPES_WITH_A_STAGE_NAME_FIELD = frozenset({"PipelineStage"})


def flow_stage_label(node_id: str, nodes_by_id: dict[str, Any]) -> str:
    node = nodes_by_id.get(node_id)
    if not node:
        return node_id
    values = node.get("values") or {}
    node_type = node.get("type")

    keys = _RENAME_VALUE_KEYS
    if isinstance(node_type, str) and node_type in _TYPES_WITH_A_STAGE_NAME_FIELD:
        keys = (*_RENAME_VALUE_KEYS, *_STAGE_NAME_VALUE_KEYS)

    for key in keys:
        candidate = values.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return _prettify(node_type) if isinstance(node_type, str) and node_type else node_id
