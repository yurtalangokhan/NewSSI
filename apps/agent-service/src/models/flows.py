"""Pydantic models for the agent flow canvas.

Two contracts live here:

- ``FlowSpec`` — what a saved flow looks like (nodes, edges, values only).
- ``ComponentTemplate`` — what a node type looks like (fields and ports).

Schemas live only on the server. A saved ``FlowSpec`` stores *values*, never the
field descriptors, so changing a template can never desynchronise a stored flow.

See ``.tmp/flow-canvas-design.md`` sections 4.2 and 4.4.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FieldType(str, Enum):
    """Input field types. Each maps to one refresh-components input."""

    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    SLIDER = "slider"
    OPTIONS = "options"
    MULTISELECT = "multiselect"
    SECRET = "secret"
    PROMPT = "prompt"
    CODE = "code"
    TABLE = "table"
    FILE = "file"
    JSON = "json"


class PortType(str, Enum):
    """Handle port types. Govern which edges may connect."""

    MESSAGE = "Message"
    TEXT = "Text"
    DOCUMENTS = "Documents"
    TOOLS = "Tools"
    MODEL = "Model"
    MEMORY = "Memory"
    AGENT = "Agent"
    DATA = "Data"
    # Langflow's vocabulary: its `Data` is displayed as "JSON" and its
    # `DataFrame` as "Table". DATA is our Data/JSON; DATAFRAME carries a table.
    DATAFRAME = "DataFrame"
    TRIGGER = "Trigger"


class ComponentKind(str, Enum):
    """Whether a component becomes a graph node or is injected at build time."""

    EXECUTION = "execution"
    RESOURCE = "resource"


class Lifecycle(str, Enum):
    """Component lifecycle state. Drives sidebar visibility and publish rules."""

    STABLE = "stable"
    BETA = "beta"
    DEPRECATED = "deprecated"


class NodePosition(BaseModel):
    """Canvas coordinates for a node."""

    x: float = 0
    y: float = 0


class Viewport(BaseModel):
    """Canvas pan and zoom state."""

    x: float = 0
    y: float = 0
    zoom: float = 1


class FlowNode(BaseModel):
    """One node in a saved flow. Carries values only — never field descriptors."""

    id: str
    type: str
    template_version: int = 1
    position: NodePosition = Field(default_factory=NodePosition)
    values: dict[str, Any] = Field(default_factory=dict)


class FlowEdge(BaseModel):
    """One connection in a saved flow.

    Handle fields use camel-case aliases because that is what ``@xyflow/react``
    emits; matching it avoids a translation layer in the client.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str
    source: str
    source_handle: str = Field(alias="sourceHandle")
    target: str
    target_handle: str = Field(alias="targetHandle")


class FlowSpec(BaseModel):
    """A saved flow: nodes, edges, and canvas viewport.

    Node ids are unique and every edge resolves to a known node. Both are
    enforced here rather than downstream, because the validator, the compiler
    and the canvas all assume it.
    """

    version: str = "1.0"
    nodes: list[FlowNode] = Field(default_factory=list)
    edges: list[FlowEdge] = Field(default_factory=list)
    viewport: Viewport | None = None

    @model_validator(mode="after")
    def _check_node_ids_unique(self) -> FlowSpec:
        seen: set[str] = set()
        duplicates: list[str] = []
        for node in self.nodes:
            if node.id in seen and node.id not in duplicates:
                duplicates.append(node.id)
            seen.add(node.id)
        if duplicates:
            raise ValueError(f"duplicate node ids: {', '.join(sorted(duplicates))}")
        return self

    @model_validator(mode="after")
    def _check_edges_resolve(self) -> FlowSpec:
        node_ids = {node.id for node in self.nodes}
        missing: list[str] = []
        for edge in self.edges:
            for endpoint in (edge.source, edge.target):
                if endpoint not in node_ids and endpoint not in missing:
                    missing.append(endpoint)
        if missing:
            raise ValueError(f"edges reference unknown nodes: {', '.join(sorted(missing))}")
        return self


class TableColumn(BaseModel):
    """One column of a TABLE field, so the canvas need not hardcode the
    column names of each component type.

    ``type`` and ``options`` mirror Langflow's ``table_schema``: without them
    every cell is a free-text box, which is how a mistyped Router operator
    could reach a saved flow and then silently never match.
    """

    name: str
    display_name: str
    type: FieldType = FieldType.STR
    options: list[str] | None = None


class ShowWhen(BaseModel):
    """Conditional visibility for a field or an output handle, judged against
    sibling values.

    Every clause that is set must hold. Deliberately tiny: this is display
    logic, not a rules engine. A hidden field keeps its stored value — only
    rendering and the required-input check change.
    """

    field: str
    equals: Any | None = None
    not_equals: Any | None = None
    one_of: list[Any] | None = None
    not_one_of: list[Any] | None = None


class Handle(BaseModel):
    """A named port on a component, accepting or emitting a set of port types.

    ``expands_from`` turns one declared port into a family: the canvas and the
    validator replace it with one handle per row of that field, named by the
    row's ``expands_label_key`` column. ``show_when`` makes an output handle
    conditional on a sibling field (e.g. Smart Router's ``else`` port only
    exists when ``enable_else_output`` is on). Declaring both here keeps them
    out of per-component special cases on both sides of the wire.
    """

    name: str
    types: list[PortType]
    expands_from: str | None = None
    expands_label_key: str | None = None
    show_when: ShowWhen | None = None
    fallback_field: str | None = None
    """The input field read when no edge is wired to this port.

    Langflow's ``MessageInput`` is at once an inline field and a port; this is
    how that shape is expressed here. Precedence is always the same: a wired
    port wins, otherwise this field. It may equal the handle's own name —
    ``inputs`` and ``handles.inputs`` are separate namespaces, and for a value
    that is genuinely "one concept, two faces" sharing the name is the honest
    declaration.
    """

    @model_validator(mode="after")
    def _check_expansion_is_complete(self) -> Handle:
        if (self.expands_from is None) != (self.expands_label_key is None):
            raise ValueError("expands_from and expands_label_key must be set together")
        return self


class ComponentHandles(BaseModel):
    """The input and output ports of a component."""

    inputs: list[Handle] = Field(default_factory=list)
    outputs: list[Handle] = Field(default_factory=list)


class InputField(BaseModel):
    """One configurable field on a component, rendered as a form input."""

    type: FieldType
    display_name: str
    required: bool = False
    value: Any = None
    options: list[str] | None = None
    options_source: str | None = None
    info: str | None = None
    advanced: bool = False
    min: float | None = None
    max: float | None = None
    step: float | None = None
    show_when: ShowWhen | None = None
    columns: list[TableColumn] | None = None
    depends_on: list[str] | None = None
    """Sibling fields this field's ``options_source`` depends on.

    Their current values are passed to the resolver (and into its cache key),
    so a dependent list is narrowed on the server. Before this the canvas
    filtered ``llm.models`` client-side by splitting a display string, which
    matched by substring and silently fell back to every provider's models.
    """

    @model_validator(mode="after")
    def _check_columns_only_on_table(self) -> InputField:
        if self.columns and self.type is not FieldType.TABLE:
            raise ValueError("only table fields may declare columns")
        return self

    @model_validator(mode="after")
    def _check_slider_bounds(self) -> InputField:
        if self.type is FieldType.SLIDER and (self.min is None or self.max is None):
            raise ValueError("slider fields require both min and max bounds")
        return self

    @model_validator(mode="after")
    def _check_choices_available(self) -> InputField:
        choice_types = (FieldType.OPTIONS, FieldType.MULTISELECT)
        if self.type in choice_types and not self.options and not self.options_source:
            raise ValueError(
                f"{self.type.value} fields require either static 'options' "
                "or an 'options_source' to resolve at runtime"
            )
        return self


class ComponentTemplate(BaseModel):
    """The server-side schema for one node type."""

    type: str
    category: str
    display_name: str
    description: str = ""
    icon: str | None = None
    template_version: int = 1
    lifecycle: Lifecycle = Lifecycle.STABLE
    kind: ComponentKind
    inputs: dict[str, InputField] = Field(default_factory=dict)
    handles: ComponentHandles
    tool_mode_field: str | None = None
    """The boolean field that flips this component into an agent tool.

    Declared per template rather than assumed for all: a control-flow node has
    no meaning as a tool, and a component that does not declare this does not
    have the capability at all — it is not a partial version of one.
    """

    @model_validator(mode="after")
    def _check_has_a_handle(self) -> ComponentTemplate:
        if not self.handles.inputs and not self.handles.outputs:
            raise ValueError(
                f"component '{self.type}' declares no handle; "
                "a node with neither an input nor an output handle cannot be wired"
            )
        return self
