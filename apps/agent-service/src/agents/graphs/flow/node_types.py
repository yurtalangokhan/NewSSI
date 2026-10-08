"""Canvas node types, and which of them may become a timeline stage.

The vocabulary is owned here because two modules need the same answer and
neither may import the other: ``builder`` compiles the canvas and already imports
``helpers``, while ``helpers`` walks the compiled graph back to the node that
produced the answer.

It used to be declared twice — once per module — and the copies drifted. The
``message_flow`` copy listed ``Foreach``, a name retired when the counter loop
became ``While``
(``service.flow_model.templates.migrations_core.register_type_rename``), and it
listed ``RunFlow``, which is a stage and not a passthrough; it also lacked
``Router`` and ``While``, which the compiler does emit. The set therefore has one
definition and both modules import it.
"""

from __future__ import annotations

from typing import Final

#: Routing nodes decide where control goes. They carry no answer of their own.
ROUTER_NODE_TYPES: Final[tuple[str, ...]] = (
    "Router",
    "Loop",
    "While",
    "ConditionalRouter",
    "SmartRouter",
    "HumanInput",
    "Guardrails",
)

#: The canvas entry and exit points.
BOUNDARY_NODE_TYPES: Final[tuple[str, ...]] = ("ChatInput", "ChatOutput")

#: Nodes that forward, transform, or only hold a value. A stage walk must keep
#: going through them instead of stopping, and the timeline must not open a
#: numbered group for them — either way the chat grows an empty stage.
PASSTHROUGH_NODE_TYPES: Final[frozenset[str]] = frozenset(
    {
        *ROUTER_NODE_TYPES,
        *BOUNDARY_NODE_TYPES,
        "Merge",
        "PromptTemplate",
        "TextInput",
        "SetVariable",
        # Processing nodes transform and forward; the answer comes from whatever
        # consumes them, so a stage walk must not stop here.
        "Operations",
        "SplitText",
        "TypeConverter",
        "Parser",
        "BatchRun",
    }
)

#: Nodes the compiler replaces with a no-op: the exit marker, and the legacy
#: ``Router`` name that predates ``ConditionalRouter`` / ``SmartRouter``.
NOOP_NODE_TYPES: Final[frozenset[str]] = frozenset({"ChatOutput", "Router"})

# ``RunFlow`` is deliberately absent above. A nested flow is a stage: it reasons,
# it produces the answer it hands over, and the chat shows its own timeline group
# (``tests/agents/test_parallel_merge_final_stage.py`` pins both the reasoning
# deltas and the token suppression for parallel RunFlow branches). Listing it as
# passthrough — as the ``helpers`` copy did — hid those stages entirely.
