"""Flow validator — every check from design spec section 4.7.

Runs on save, on publish, and on compile (P2/P3). Pure: no I/O, no database,
no registry mutation. Resource *existence* (does collection X exist, can this
user see it) needs I/O and lives in Task 5's resolvers, not here.

Two checks — nested-flow references and the send_email/mail-config rule —
reference node shapes that have no registered template until P6 and P5
respectively. Both are implemented against the *shape* of ``node.values``
rather than a specific ``node.type``, so the rule is exercised now and needs
no change when those templates land. See ``.tmp/flow-canvas-task-3-report.md``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from core.exceptions import UnknownComponentError
from domain.flows.comparison import CONDITION_OPERATORS
from domain.flows.guardrails import GUARDRAIL_DESCRIPTIONS
from domain.flows.handle_types import handles_compatible
from domain.flows.handles import (
    effective_output_handles,
    field_visible,
    resolved_values,
)
from domain.flows.output_schema import schema_errors
from domain.flows.registry import get_registry
from models.flows import ComponentKind, ComponentTemplate, FlowNode, FlowSpec, Handle

FLOW_NO_ENTRY = "FLOW_NO_ENTRY"
FLOW_MULTIPLE_ENTRY = "FLOW_MULTIPLE_ENTRY"
FLOW_NO_EXIT = "FLOW_NO_EXIT"
FLOW_ORPHAN_NODE = "FLOW_ORPHAN_NODE"
FLOW_TYPE_MISMATCH = "FLOW_TYPE_MISMATCH"
FLOW_MISSING_INPUT = "FLOW_MISSING_INPUT"
FLOW_ILLEGAL_CYCLE = "FLOW_ILLEGAL_CYCLE"
FLOW_UNBOUNDED_LOOP = "FLOW_UNBOUNDED_LOOP"
FLOW_UNKNOWN_COMPONENT = "FLOW_UNKNOWN_COMPONENT"
FLOW_NESTED_FLOW_REF = "FLOW_NESTED_FLOW_REF"
FLOW_MAIL_CONFIG_REQUIRED = "FLOW_MAIL_CONFIG_REQUIRED"
FLOW_CONDROUTER_MISSING_BRANCH = "FLOW_CONDROUTER_MISSING_BRANCH"
FLOW_CONDROUTER_DEFAULT_LOOPS = "FLOW_CONDROUTER_DEFAULT_LOOPS"
FLOW_INVALID_OPTION = "FLOW_INVALID_OPTION"
FLOW_INVALID_VARIABLE_NAME = "FLOW_INVALID_VARIABLE_NAME"
FLOW_SMART_ROUTER_MISSING_ROUTE = "FLOW_SMART_ROUTER_MISSING_ROUTE"
FLOW_SMART_ROUTER_ELSE_DISABLED = "FLOW_SMART_ROUTER_ELSE_DISABLED"
FLOW_HUMAN_INPUT_MISSING_ACTION = "FLOW_HUMAN_INPUT_MISSING_ACTION"
FLOW_HUMAN_INPUT_UNMATCHED_DISABLED = "FLOW_HUMAN_INPUT_UNMATCHED_DISABLED"
FLOW_FOREACH_MISSING_BRANCH = "FLOW_FOREACH_MISSING_BRANCH"
FLOW_GUARDRAILS_MISSING_BRANCH = "FLOW_GUARDRAILS_MISSING_BRANCH"
FLOW_GUARDRAILS_NO_CHECK = "FLOW_GUARDRAILS_NO_CHECK"
FLOW_FOREACH_BODY_NOT_LOOPING = "FLOW_FOREACH_BODY_NOT_LOOPING"
FLOW_NESTED_LOOP = "FLOW_NESTED_LOOP"
# Every FLOW_RUNFLOW_* code lives here even though three of them are raised
# from FlowService: one home per code, so a caller never has to know which
# layer produced it.
FLOW_RUNFLOW_MISSING_TARGET = "FLOW_RUNFLOW_MISSING_TARGET"
FLOW_RUNFLOW_CYCLE = "FLOW_RUNFLOW_CYCLE"
FLOW_RUNFLOW_UNPUBLISHED = "FLOW_RUNFLOW_UNPUBLISHED"
FLOW_RUNFLOW_HITL = "FLOW_RUNFLOW_HITL"
FLOW_STRUCTURED_OUTPUT_SCHEMA = "FLOW_STRUCTURED_OUTPUT_SCHEMA"
FLOW_TOOL_MODE_FLOW_EDGE = "FLOW_TOOL_MODE_FLOW_EDGE"
FLOW_TOOL_MODE_UNUSED = "FLOW_TOOL_MODE_UNUSED"

_CHAT_INPUT = "ChatInput"
_CHAT_OUTPUT = "ChatOutput"
_LOOP = "Loop"  # foreach
_WHILE = "While"  # counter loop
_CONDITIONAL_ROUTER = "ConditionalRouter"
_GUARDRAILS = "Guardrails"
_GUARDRAILS_BRANCHES = ("pass_result", "fail_result")
_RUN_FLOW = "RunFlow"
_STRUCTURED_OUTPUT = "StructuredOutput"
_OPERATIONS = "Operations"
_TOOL_HANDLE = "tool"
_ROUTER = "Router"
_MAIL_TOOLS = "MailTools"
_MAIL_CONFIG = "MailConfig"
_SEND_EMAIL_TOOL = "send_email"
# Node types whose max_iterations is a mandatory R2 bound.
_ITERATING_TYPES = (_WHILE, _CONDITIONAL_ROUTER)
# Node types whose own outgoing edges are a sanctioned cycle back-reference
# (a While's counter loop, an If-Else loop, a Loop's foreach body).
_CYCLE_OWNER_TYPES = (_LOOP, _WHILE, _CONDITIONAL_ROUTER)
# The two ConditionalRouter branch handles — also the only valid values for
# its ``default_route`` field.
_CONDROUTER_BRANCHES = ("true_result", "false_result")
_VALID_DEFAULT_ROUTES = _CONDROUTER_BRANCHES

_VARIABLE_NODE_TYPES = ("SetVariable",)
# A variable name must be a valid str.format placeholder so PromptTemplate can
# read it as {name}; it must start with a letter, because internal counter keys
# start with an underscore; and it cannot contain a dash, because node ids do.
# One rule, three collisions avoided.
_VARIABLE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class ValidationIssue:
    """One problem found in a flow, attributed to a node or edge where possible."""

    code: str
    message: str
    node_id: str | None = None
    edge_id: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """The wire shape every flow endpoint returns issues in."""
        return {
            "code": self.code,
            "message": self.message,
            "node_id": self.node_id,
            "edge_id": self.edge_id,
        }


@dataclass(frozen=True)
class ValidationResult:
    """The full result of validating a flow. Reports everything, not just the first hit."""

    valid: bool
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)


def _resolved_value(node: FlowNode, template: ComponentTemplate | None, name: str) -> Any:
    """The effective value for a field: node override, else template default."""
    if name in node.values:
        return node.values[name]
    if template is not None and name in template.inputs:
        return template.inputs[name].value
    return None


def _find_handle(handles: list[Handle], name: str) -> Handle | None:
    return next((h for h in handles if h.name == name), None)


def _resolve_templates(
    spec: FlowSpec, errors: list[ValidationIssue]
) -> dict[str, ComponentTemplate | None]:
    registry = get_registry()
    templates: dict[str, ComponentTemplate | None] = {}
    for node in spec.nodes:
        if node.type in ("note", "noteNode"):
            continue
        try:
            templates[node.id] = registry.get(node.type)
        except UnknownComponentError:
            templates[node.id] = None
            errors.append(
                ValidationIssue(
                    FLOW_UNKNOWN_COMPONENT,
                    f"Node '{node.id}' has unknown component type '{node.type}'",
                    node_id=node.id,
                )
            )
    return templates


def _resource_node_ids(templates: dict[str, ComponentTemplate | None]) -> set[str]:
    """Node ids whose registered template is a resource.

    Mirrors FlowGraphBuilder/partition_nodes: the compiler extracts exactly
    these nodes from the execution graph, so any edge touching one is
    build-time wiring (injected into a consumer), never a graph edge.
    """
    return {
        node_id
        for node_id, template in templates.items()
        if template is not None and template.kind is ComponentKind.RESOURCE
    }


def _forward_adjacency(spec: FlowSpec, resource_ids: set[str]) -> dict[str, list[str]]:
    """Execution-only adjacency.

    Edges touching a resource node are skipped — the same partition rule the
    compiler applies when adding graph edges (flow_builder.py build()).
    Walking through a resource here would make validation disagree with the
    compiled graph: a flow like ChatInput → Model → ChatOutput would validate
    but compile into a dead-end graph that silently echoes the input.
    """
    adjacency: dict[str, list[str]] = {node.id: [] for node in spec.nodes}
    for edge in spec.edges:
        if edge.source in resource_ids or edge.target in resource_ids:
            continue  # resource wiring — injected at build time, not a graph edge
        adjacency[edge.source].append(edge.target)
    return adjacency


def _reachable_from(start_ids: list[str], adjacency: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(start_ids)
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(adjacency.get(current, []))
    return seen


def _check_structure(
    spec: FlowSpec,
    templates: dict[str, ComponentTemplate | None],
    errors: list[ValidationIssue],
    warnings: list[ValidationIssue],
) -> None:
    """Entry/exit cardinality, reachability, and orphan nodes — one pass."""
    entries = [n for n in spec.nodes if n.type == _CHAT_INPUT]

    if not entries:
        errors.append(ValidationIssue(FLOW_NO_ENTRY, "Flow has no Chat Input node"))
        return
    if len(entries) > 1:
        errors.append(
            ValidationIssue(
                FLOW_MULTIPLE_ENTRY,
                f"Flow has {len(entries)} Chat Input nodes; exactly one is required",
            )
        )

    adjacency = _forward_adjacency(spec, _resource_node_ids(templates))
    reached = _reachable_from([n.id for n in entries], adjacency)

    has_exit = any(n.type == _CHAT_OUTPUT and n.id in reached for n in spec.nodes)
    if not has_exit:
        errors.append(
            ValidationIssue(
                FLOW_NO_EXIT,
                "No Chat Output node is reachable from Chat Input through execution "
                "nodes; resource nodes (models, tools, memory) are injected at build "
                "time and cannot forward the flow",
            )
        )

    for node in spec.nodes:
        if node.type in ("note", "noteNode") or node.id in reached or node.type == _CHAT_INPUT:
            continue
        template = templates.get(node.id)
        if template is not None and template.kind is ComponentKind.RESOURCE:
            continue  # resources are providers, not part of the reachability chain
        warnings.append(
            ValidationIssue(
                FLOW_ORPHAN_NODE,
                f"Node '{node.id}' ({node.type}) is not reachable from Chat Input",
                node_id=node.id,
            )
        )


def _check_edge_types(
    spec: FlowSpec,
    templates: dict[str, ComponentTemplate | None],
    errors: list[ValidationIssue],
) -> None:
    nodes_by_id = {n.id: n for n in spec.nodes}
    for edge in spec.edges:
        source_template = templates.get(edge.source)
        target_template = templates.get(edge.target)
        if source_template is None or target_template is None:
            continue  # unknown component already reported

        source_node = nodes_by_id.get(edge.source)
        source_handle = _find_handle(
            effective_output_handles(source_template, source_node.values if source_node else {}),
            edge.source_handle,
        )
        target_handle = _find_handle(target_template.handles.inputs, edge.target_handle)
        if source_handle is None or target_handle is None:
            continue  # unknown handle name — a canvas-side legality bug, not this task's scope

        if not handles_compatible(source_handle.types, target_handle.types):
            source_names = [t.value for t in source_handle.types]
            target_names = [t.value for t in target_handle.types]
            errors.append(
                ValidationIssue(
                    FLOW_TYPE_MISMATCH,
                    f"Edge '{edge.id}' connects incompatible types "
                    f"{source_names} -> {target_names}",
                    edge_id=edge.id,
                )
            )


def _check_required_inputs(
    spec: FlowSpec,
    templates: dict[str, ComponentTemplate | None],
    errors: list[ValidationIssue],
) -> None:
    for node in spec.nodes:
        template = templates.get(node.id)
        if template is None:
            continue
        resolved = resolved_values(template, node.values)
        for name, input_field in template.inputs.items():
            if not input_field.required:
                continue
            if not field_visible(input_field, resolved):
                continue  # a hidden field cannot be filled in; requiring it is a trap
            if node.type in _ITERATING_TYPES and name == "max_iterations":
                continue  # dedicated, more actionable check — _check_iteration_bounds
            value = _resolved_value(node, template, name)
            if value in (None, ""):
                # Check if satisfied by an incoming edge to this handle
                if any(e.target == node.id and e.target_handle == name for e in spec.edges):
                    continue
                errors.append(
                    ValidationIssue(
                        FLOW_MISSING_INPUT,
                        f"Node '{node.id}' ({node.type}) is missing required input '{name}'",
                        node_id=node.id,
                    )
                )


def _check_iteration_bounds(
    spec: FlowSpec,
    templates: dict[str, ComponentTemplate | None],
    errors: list[ValidationIssue],
) -> None:
    """Every node that can own a cycle (Loop, ConditionalRouter) must carry a
    positive max_iterations — the R2 ("no infinite loop") guarantee."""
    for node in spec.nodes:
        if node.type not in _ITERATING_TYPES:
            continue
        template = templates.get(node.id)
        value = _resolved_value(node, template, "max_iterations")
        if value is None or (isinstance(value, int | float) and value <= 0):
            errors.append(
                ValidationIssue(
                    FLOW_UNBOUNDED_LOOP,
                    f"{node.type} node '{node.id}' has no positive max_iterations bound",
                    node_id=node.id,
                )
            )


def _has_cycle(adjacency: dict[str, list[str]]) -> bool:
    white, gray, black = 0, 1, 2
    color = dict.fromkeys(adjacency, white)

    for start in adjacency:
        if color[start] != white:
            continue
        stack: list[tuple[str, Iterator[str]]] = [(start, iter(adjacency[start]))]
        color[start] = gray
        while stack:
            node_id, neighbors = stack[-1]
            advanced = False
            for nxt in neighbors:
                state = color.get(nxt, white)
                if state == gray:
                    return True
                if state == white:
                    color[nxt] = gray
                    stack.append((nxt, iter(adjacency.get(nxt, []))))
                    advanced = True
                    break
            if not advanced:
                color[node_id] = black
                stack.pop()
    return False


def _check_cycles(
    spec: FlowSpec,
    templates: dict[str, ComponentTemplate | None],
    errors: list[ValidationIssue],
) -> None:
    iterating_ids = {n.id for n in spec.nodes if n.type in _CYCLE_OWNER_TYPES}
    resource_ids = _resource_node_ids(templates)
    adjacency: dict[str, list[str]] = {n.id: [] for n in spec.nodes}
    for edge in spec.edges:
        if edge.source in iterating_ids:
            continue  # a Loop / While / If-Else's own outgoing edges are the
            # sanctioned back-reference
        if edge.source in resource_ids or edge.target in resource_ids:
            continue  # resource wiring is injected at build time, never an execution cycle
        adjacency[edge.source].append(edge.target)

    if _has_cycle(adjacency):
        errors.append(
            ValidationIssue(
                FLOW_ILLEGAL_CYCLE,
                "Flow contains a cycle not routed through a Loop or If-Else node",
            )
        )


def _check_conditional_router(
    spec: FlowSpec,
    templates: dict[str, ComponentTemplate | None],
    errors: list[ValidationIssue],
) -> None:
    """ConditionalRouter-specific rules:

    - both ``true_result`` and ``false_result`` must be wired (our
      ``default_route`` fallback needs both branches to exist);
    - ``operator`` / ``default_route`` must hold a known value;
    - the ``default_route`` branch must not lead back to the router — that
      would make hitting the bound spin forever instead of breaking the loop.
    """
    cr_nodes = [n for n in spec.nodes if n.type == _CONDITIONAL_ROUTER]
    if not cr_nodes:
        return

    adjacency = _forward_adjacency(spec, _resource_node_ids(templates))
    outgoing_by_handle: dict[str, dict[str, str]] = {}
    for edge in spec.edges:
        if edge.source in {n.id for n in cr_nodes}:
            outgoing_by_handle.setdefault(edge.source, {})[edge.source_handle] = edge.target

    for node in cr_nodes:
        template = templates.get(node.id)
        handles = outgoing_by_handle.get(node.id, {})

        for branch in _CONDROUTER_BRANCHES:
            if branch not in handles:
                errors.append(
                    ValidationIssue(
                        FLOW_CONDROUTER_MISSING_BRANCH,
                        f"ConditionalRouter node '{node.id}' has no '{branch}' branch wired",
                        node_id=node.id,
                    )
                )

        operator = _resolved_value(node, template, "operator")
        if operator is not None and operator not in CONDITION_OPERATORS:
            errors.append(
                ValidationIssue(
                    FLOW_INVALID_OPTION,
                    f"ConditionalRouter node '{node.id}' has unknown operator '{operator}'",
                    node_id=node.id,
                )
            )

        default_route = _resolved_value(node, template, "default_route")
        if default_route is not None and default_route not in _VALID_DEFAULT_ROUTES:
            errors.append(
                ValidationIssue(
                    FLOW_INVALID_OPTION,
                    f"ConditionalRouter node '{node.id}' has unknown default_route "
                    f"'{default_route}'",
                    node_id=node.id,
                )
            )
            continue

        default_target = handles.get(default_route or "false_result")
        if default_target is not None and node.id in _reachable_from([default_target], adjacency):
            errors.append(
                ValidationIssue(
                    FLOW_CONDROUTER_DEFAULT_LOOPS,
                    f"ConditionalRouter node '{node.id}' default_route branch "
                    f"'{default_route}' leads back to the router; once max_iterations "
                    "is hit the flow would never terminate. Point default_route at the "
                    "branch that leaves the loop.",
                    node_id=node.id,
                )
            )


def _check_variable_names(
    spec: FlowSpec,
    templates: dict[str, ComponentTemplate | None],
    errors: list[ValidationIssue],
) -> None:
    """A SetVariable name must be usable as {name} and must not collide with
    the two other families of scratch keys (node ids, internal counters)."""
    for node in spec.nodes:
        if node.type not in _VARIABLE_NODE_TYPES:
            continue
        name = _resolved_value(node, templates.get(node.id), "name")
        if not isinstance(name, str) or not _VARIABLE_NAME_RE.match(name):
            errors.append(
                ValidationIssue(
                    FLOW_INVALID_VARIABLE_NAME,
                    f"Node '{node.id}' ({node.type}) has invalid variable name "
                    f"{name!r}; use letters, digits and underscores, starting "
                    "with a letter",
                    node_id=node.id,
                )
            )


def _check_human_input(
    spec: FlowSpec,
    templates: dict[str, ComponentTemplate | None],
    errors: list[ValidationIssue],
) -> None:
    """Human Input: every action needs an outgoing branch, and the
    'unmatched' branch may only be wired when ``enable_unmatched`` is on."""
    for node in spec.nodes:
        if node.type != "HumanInput":
            continue
        wired = {e.source_handle for e in spec.edges if e.source == node.id}
        decisions = _resolved_value(node, templates.get(node.id), "decisions") or []
        for row in decisions:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label", "")).strip()
            if label and label not in wired:
                errors.append(
                    ValidationIssue(
                        FLOW_HUMAN_INPUT_MISSING_ACTION,
                        f"HumanInput node '{node.id}' action '{label}' has no "
                        "outgoing branch wired",
                        node_id=node.id,
                    )
                )
        unmatched_enabled = bool(_resolved_value(node, templates.get(node.id), "enable_unmatched"))
        if "unmatched" in wired and not unmatched_enabled:
            errors.append(
                ValidationIssue(
                    FLOW_HUMAN_INPUT_UNMATCHED_DISABLED,
                    f"HumanInput node '{node.id}' has an 'unmatched' branch wired "
                    "but 'Enable unmatched branch' is off",
                    node_id=node.id,
                )
            )


def _check_run_flow(
    spec: FlowSpec,
    templates: dict[str, ComponentTemplate | None],
    errors: list[ValidationIssue],
) -> None:
    """Run Flow: a target must be chosen.

    The only Run Flow rule that needs no I/O, so the only one that belongs in
    this pure module. Whether the target exists, is published, forms a
    reference cycle, or contains a Human Input all require reading the target
    flow itself and therefore live in ``FlowService.validate_flow``.
    """
    for node in spec.nodes:
        if node.type != _RUN_FLOW:
            continue
        target = str(_resolved_value(node, templates.get(node.id), "flow_id") or "").strip()
        if not target:
            errors.append(
                ValidationIssue(
                    FLOW_RUNFLOW_MISSING_TARGET,
                    f"RunFlow node '{node.id}' has no target flow selected",
                    node_id=node.id,
                )
            )


def _check_router_rows(
    spec: FlowSpec,
    templates: dict[str, ComponentTemplate | None],
    errors: list[ValidationIssue],
) -> None:
    """Router: every row's operator must be one the comparison language knows.

    ``evaluate_comparison`` returns False for an unknown operator on purpose —
    a routing function must not raise — so a typo means "this route never
    fires" and the flow silently falls through to ``default``. Reporting it
    here is the only place it can be seen.

    A blank operator is fine: the compiler reads it as ``is_truthy``, which is
    what the v1 migration produces.
    """
    for node in spec.nodes:
        if node.type != _ROUTER:
            continue
        rows = _resolved_value(node, templates.get(node.id), "routes") or []
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            operator = str(row.get("operator", "") or "").strip()
            if operator and operator not in CONDITION_OPERATORS:
                errors.append(
                    ValidationIssue(
                        FLOW_INVALID_OPTION,
                        f"Router node '{node.id}' row {index + 1} has unknown "
                        f"operator '{operator}'; that route would never match",
                        node_id=node.id,
                    )
                )


def _check_tool_mode(
    spec: FlowSpec,
    templates: dict[str, ComponentTemplate | None],
    errors: list[ValidationIssue],
) -> None:
    """A tool-mode node is the agent's capability, not a step in the flow.

    Two ways to get it wrong, both silent at run time: wiring it into the flow
    (the node never runs, so the edge does nothing) and wiring it to no agent
    (the tool exists and nothing can call it).
    """
    for node in spec.nodes:
        template = templates.get(node.id)
        if template is None or not template.tool_mode_field:
            continue
        if not node.values.get(template.tool_mode_field, False):
            continue

        for edge in spec.edges:
            is_flow_edge = edge.target == node.id or (
                edge.source == node.id and edge.source_handle != _TOOL_HANDLE
            )
            if is_flow_edge:
                errors.append(
                    ValidationIssue(
                        FLOW_TOOL_MODE_FLOW_EDGE,
                        f"Node '{node.id}' is used as a tool, so it does not run "
                        "as a flow step; remove the flow edge and wire only its "
                        "Tool output to an agent",
                        node_id=node.id,
                        edge_id=edge.id,
                    )
                )
                break

        if not any(e.source == node.id and e.source_handle == _TOOL_HANDLE for e in spec.edges):
            errors.append(
                ValidationIssue(
                    FLOW_TOOL_MODE_UNUSED,
                    f"Node '{node.id}' is used as a tool but its Tool output is wired to no agent",
                    node_id=node.id,
                )
            )


def _check_operations(
    spec: FlowSpec,
    templates: dict[str, ComponentTemplate | None],
    errors: list[ValidationIssue],
) -> None:
    """Data Operations: the chosen operation must be one Langflow has.

    The compiler refuses an unknown one too, but only when the flow first
    runs; reporting it here means the author sees it while editing.
    """
    from domain.flows.data_ops import ALL_OPERATIONS

    for node in spec.nodes:
        if node.type != _OPERATIONS:
            continue
        operation = _resolved_value(node, templates.get(node.id), "operation")
        if operation and operation not in ALL_OPERATIONS:
            errors.append(
                ValidationIssue(
                    FLOW_INVALID_OPTION,
                    f"Operations node '{node.id}' has unknown operation '{operation}'",
                    node_id=node.id,
                )
            )


def _check_structured_output(
    spec: FlowSpec,
    templates: dict[str, ComponentTemplate | None],
    errors: list[ValidationIssue],
) -> None:
    """Structured Output: the schema table must describe a buildable model.

    The compiler builds a Pydantic model from these rows, so a bad row is a
    build failure. Reporting it here means the author sees it while editing
    rather than the first time the flow runs.
    """
    for node in spec.nodes:
        if node.type != _STRUCTURED_OUTPUT:
            continue
        rows = _resolved_value(node, templates.get(node.id), "output_schema")
        for problem in schema_errors(rows):
            errors.append(
                ValidationIssue(
                    FLOW_STRUCTURED_OUTPUT_SCHEMA,
                    f"StructuredOutput node '{node.id}': {problem}",
                    node_id=node.id,
                )
            )


def _check_foreach_loop(
    spec: FlowSpec,
    templates: dict[str, ComponentTemplate | None],
    errors: list[ValidationIssue],
) -> None:
    """Loop (foreach) rules: both branches wired, the ``item`` branch loops
    back to the node, and no Loop sits inside another Loop's body (the
    sequential foreach machinery does not nest)."""
    loop_ids = [n.id for n in spec.nodes if n.type == _LOOP]
    if not loop_ids:
        return

    resource_ids = _resource_node_ids(templates)
    adjacency = _forward_adjacency(spec, resource_ids)

    for loop_id in loop_ids:
        outgoing = {e.source_handle: e.target for e in spec.edges if e.source == loop_id}
        for branch in ("item", "done"):
            if branch not in outgoing:
                errors.append(
                    ValidationIssue(
                        FLOW_FOREACH_MISSING_BRANCH,
                        f"Loop node '{loop_id}' has no '{branch}' branch wired",
                        node_id=loop_id,
                    )
                )

        item_target = outgoing.get("item")
        if item_target is not None:
            body = _reachable_from([item_target], adjacency)
            # The Loop has two input ports: `input` closes the body, `items`
            # carries the collection. Closing onto `items` would re-resolve the
            # collection every pass and never finish, so reachability alone is
            # not enough — the returning edge must land on `input`.
            closes_on_input = any(
                e.target == loop_id and e.target_handle == "input" and e.source in body
                for e in spec.edges
            )
            if not closes_on_input:
                errors.append(
                    ValidationIssue(
                        FLOW_FOREACH_BODY_NOT_LOOPING,
                        f"Loop node '{loop_id}' item branch never returns to the "
                        "Loop's input; wire the body's end back to the Loop's "
                        "input handle (the Items port takes the collection, not "
                        "the body's result)",
                        node_id=loop_id,
                    )
                )
            nested = [nid for nid in body if nid != loop_id and nid in loop_ids]
            for nid in nested:
                errors.append(
                    ValidationIssue(
                        FLOW_NESTED_LOOP,
                        f"Loop node '{nid}' is inside the body of Loop '{loop_id}'; "
                        "nested foreach loops are not supported",
                        node_id=nid,
                    )
                )


def _check_smart_router(
    spec: FlowSpec,
    templates: dict[str, ComponentTemplate | None],
    errors: list[ValidationIssue],
) -> None:
    """Smart Router: every category row needs an outgoing branch, and an
    'else' branch may only be wired when ``enable_else_output`` is on."""
    for node in spec.nodes:
        if node.type != "SmartRouter":
            continue
        wired = {e.source_handle for e in spec.edges if e.source == node.id}
        rows = _resolved_value(node, templates.get(node.id), "routes") or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            category = str(row.get("route_category", "")).strip()
            if category and category not in wired:
                errors.append(
                    ValidationIssue(
                        FLOW_SMART_ROUTER_MISSING_ROUTE,
                        f"SmartRouter node '{node.id}' category '{category}' has "
                        "no outgoing branch wired",
                        node_id=node.id,
                    )
                )
        else_enabled = bool(_resolved_value(node, templates.get(node.id), "enable_else_output"))
        if "else" in wired and not else_enabled:
            errors.append(
                ValidationIssue(
                    FLOW_SMART_ROUTER_ELSE_DISABLED,
                    f"SmartRouter node '{node.id}' has an 'else' branch wired but "
                    "'Enable Else output' is off",
                    node_id=node.id,
                )
            )


def _check_guardrails(
    spec: FlowSpec,
    templates: dict[str, ComponentTemplate | None],
    errors: list[ValidationIssue],
) -> None:
    """Guardrails: both verdict branches must be wired, and at least one check
    must actually be enabled.

    Both branches, because the node exists to split: a blocked input with no
    Fail branch has nowhere to go, and the run would end without an answer.
    The check requirement is caught here rather than at run time so the message
    names the node while the author is still looking at it. An unrecognised
    guardrail name matters for the same reason the Router's operator does — the
    runtime drops it silently, leaving a check the author believes is running.
    """
    for node in spec.nodes:
        if node.type != _GUARDRAILS:
            continue
        template = templates.get(node.id)
        wired = {e.source_handle for e in spec.edges if e.source == node.id}
        for branch in _GUARDRAILS_BRANCHES:
            if branch not in wired:
                errors.append(
                    ValidationIssue(
                        FLOW_GUARDRAILS_MISSING_BRANCH,
                        f"Guardrails node '{node.id}' has no '{branch}' branch wired",
                        node_id=node.id,
                    )
                )

        enabled = _resolved_value(node, template, "enabled_guardrails") or []
        if not isinstance(enabled, list):
            enabled = []
        for name in enabled:
            if name not in GUARDRAIL_DESCRIPTIONS:
                errors.append(
                    ValidationIssue(
                        FLOW_INVALID_OPTION,
                        f"Guardrails node '{node.id}' has unknown guardrail "
                        f"'{name}'; that check would never run",
                        node_id=node.id,
                    )
                )

        custom = (
            str(_resolved_value(node, template, "custom_guardrail_explanation") or "")
            if _resolved_value(node, template, "enable_custom_guardrail")
            else ""
        )
        known = [name for name in enabled if name in GUARDRAIL_DESCRIPTIONS]
        if not known and not custom.strip():
            errors.append(
                ValidationIssue(
                    FLOW_GUARDRAILS_NO_CHECK,
                    f"Guardrails node '{node.id}' has no guardrail enabled; "
                    "select at least one, or describe a custom one",
                    node_id=node.id,
                )
            )


def _check_agent_ref(
    spec: FlowSpec,
    is_flow_backed: Callable[[str], bool] | None,
    errors: list[ValidationIssue],
) -> None:
    if is_flow_backed is None:
        return
    for node in spec.nodes:
        agent_ids: list[str] = []
        single_agent = node.values.get("agent_id")
        if single_agent:
            agent_ids.append(str(single_agent))
        sub_agents = node.values.get("sub_agents")
        if isinstance(sub_agents, list):
            agent_ids.extend(str(s) for s in sub_agents if s)
        elif isinstance(sub_agents, str) and sub_agents:
            agent_ids.append(sub_agents)

        for agent_id in agent_ids:
            if is_flow_backed(agent_id):
                errors.append(
                    ValidationIssue(
                        FLOW_NESTED_FLOW_REF,
                        f"Node '{node.id}' references agent '{agent_id}', which is itself "
                        "flow-backed; a flow cannot reference another flow",
                        node_id=node.id,
                    )
                )


def _check_mail_config(spec: FlowSpec, errors: list[ValidationIssue]) -> None:
    # 1. Classic persona-shaped check (agent-level mcp_tools & mcp_tool_configs)
    for node in spec.nodes:
        tools = node.values.get("mcp_tools") or []
        if _SEND_EMAIL_TOOL not in tools:
            continue
        mail_config_id = (
            (node.values.get("mcp_tool_configs") or {})
            .get(_SEND_EMAIL_TOOL, {})
            .get("mail_config_id")
        )
        if not mail_config_id:
            errors.append(
                ValidationIssue(
                    FLOW_MAIL_CONFIG_REQUIRED,
                    f"Node '{node.id}' enables send_email but has no bound mail config",
                    node_id=node.id,
                )
            )

    # 2. Graph-shaped check (MailTools resource node with send_email enabled)
    nodes_by_id = {n.id: n for n in spec.nodes}
    for node in spec.nodes:
        if node.type != _MAIL_TOOLS:
            continue
        selected_tools = node.values.get("tools") or []
        if _SEND_EMAIL_TOOL not in selected_tools:
            continue

        has_wired_config = False
        for edge in spec.edges:
            if edge.target == node.id:
                source_node = nodes_by_id.get(edge.source)
                if source_node and source_node.type == _MAIL_CONFIG:
                    cfg_id = source_node.values.get("config_id")
                    if cfg_id and str(cfg_id).strip():
                        has_wired_config = True
                        break

        if not has_wired_config:
            errors.append(
                ValidationIssue(
                    FLOW_MAIL_CONFIG_REQUIRED,
                    f"MailTools node '{node.id}' enables send_email but has no configured MailConfig wired",
                    node_id=node.id,
                )
            )


def validate(
    spec: FlowSpec,
    *,
    is_flow_backed: Callable[[str], bool] | None = None,
) -> ValidationResult:
    """Validate a flow. Accumulates every issue instead of stopping at the first."""
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    templates = _resolve_templates(spec, errors)

    _check_structure(spec, templates, errors, warnings)
    _check_edge_types(spec, templates, errors)
    _check_required_inputs(spec, templates, errors)
    _check_iteration_bounds(spec, templates, errors)
    _check_cycles(spec, templates, errors)
    _check_conditional_router(spec, templates, errors)
    _check_variable_names(spec, templates, errors)
    _check_foreach_loop(spec, templates, errors)
    _check_smart_router(spec, templates, errors)
    _check_human_input(spec, templates, errors)
    _check_run_flow(spec, templates, errors)
    _check_structured_output(spec, templates, errors)
    _check_operations(spec, templates, errors)
    _check_tool_mode(spec, templates, errors)
    _check_router_rows(spec, templates, errors)
    _check_guardrails(spec, templates, errors)
    _check_agent_ref(spec, is_flow_backed, errors)
    _check_mail_config(spec, errors)

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)
