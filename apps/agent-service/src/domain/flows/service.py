"""Flow orchestration service.

Combines the pure pieces from Tasks 1-5 into what the HTTP layer needs:
listing/reading templates, resolving options, validating a flow (structural
checks plus the resource-existence check that needs I/O), and persisting a
flow with template values migrated to their current version.

Route → service → repository. This module raises domain errors only; routes
translate them to HTTP.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from agents.graphs.schemas import GraphSchemaType
from core.exceptions import FlowValidationError, FlowVersionConflictError
from domain.flows.migrations import migrate_spec
from domain.flows.references import flow_references
from domain.flows.registry import ComponentRegistry, get_registry
from domain.flows.resolvers import (
    ResolvedOptions,
    ResolverContext,
    resolve_options,
    resource_exists,
)
from domain.flows.validator import (
    FLOW_RUNFLOW_CYCLE,
    FLOW_RUNFLOW_HITL,
    FLOW_RUNFLOW_UNPUBLISHED,
    ValidationIssue,
    ValidationResult,
    validate,
)
from models.flows import ComponentTemplate, FlowSpec

FLOW_UNKNOWN_RESOURCE = "FLOW_UNKNOWN_RESOURCE"


class FlowService:
    """Orchestrates the flow-canvas domain modules for the API layer."""

    def __init__(
        self,
        *,
        registry: ComponentRegistry | None = None,
        repository: Any = None,
        version_repository: Any = None,
    ) -> None:
        self._registry = registry or get_registry()
        self._repository = repository
        self._version_repository = version_repository

    # -- Components -----------------------------------------------------

    def list_components(self) -> dict[str, list[ComponentTemplate]]:
        """All registered templates, grouped by category."""
        return self._registry.list_grouped()

    def get_component(self, component_type: str) -> ComponentTemplate:
        """A single template by type. Raises UnknownComponentError if absent."""
        return self._registry.get(component_type)

    # -- Options ----------------------------------------------------------

    async def resolve_options(self, source: str, context: ResolverContext) -> ResolvedOptions:
        """Resolve one options_source for the calling user."""
        return await resolve_options(source, context)

    # -- Validation ---------------------------------------------------------

    async def validate_flow(
        self,
        spec: FlowSpec,
        context: ResolverContext,
        *,
        is_flow_backed: Callable[[str], bool] | None = None,
        definition_id: UUID | str | None = None,
    ) -> ValidationResult:
        """Structural validation (Task 3, pure) plus resource-existence (Task 5, I/O).

        ``definition_id`` names the flow being validated, which is what makes
        "a reference that comes back here" meaningful. It stays optional so
        every existing caller keeps working; only publish knows which
        definition it is publishing. The target checks need no id and
        therefore run for everyone — including the pre-flight /validate-flow
        route, which is exactly where an author wants to hear that a target is
        unpublished.
        """
        structural = validate(spec, is_flow_backed=is_flow_backed)
        resource_issues = await self._check_resource_references(spec, context)
        reference_issues = await self._check_run_flow_targets(spec)
        cycle_issues: list[ValidationIssue] = []
        if definition_id is not None:
            cycle_issues = await self._check_flow_reference_cycle(
                spec, definition_id=str(definition_id)
            )
        errors = [*structural.errors, *resource_issues, *reference_issues, *cycle_issues]
        return ValidationResult(valid=not errors, errors=errors, warnings=structural.warnings)

    # -- Run Flow reference checks (Phase 5) ------------------------------
    #
    # These need I/O — they read *other* flows — so they cannot live in the
    # pure validator. validate_flow already mixes the pure result with
    # resource-existence checks, and publish_flow calls it, so this is the
    # existing seam rather than a new one.

    async def _load_reference_spec(self, definition_id: str) -> FlowSpec | None:
        """The published spec of a referenced flow, or None when there is none.

        ``agent_definitions.flow_spec`` is the denormalized cache of the
        published version, so "no flow_spec" is exactly "never published".
        """
        if self._repository is None:
            return None
        try:
            definition = await self._repository.get_by_id(UUID(str(definition_id)))
        except (ValueError, TypeError, AttributeError):
            return None
        if definition is None or not getattr(definition, "flow_spec", None):
            return None
        try:
            return FlowSpec.model_validate(definition.flow_spec)
        except Exception:  # noqa: BLE001 - a corrupt stored spec is not a crash here
            return None

    async def _check_flow_reference_cycle(
        self, spec: FlowSpec, *, definition_id: str
    ) -> list[ValidationIssue]:
        """Reject a Run Flow reference that can reach its own flow again.

        This walks the *reference* graph — definitions as vertices, Run Flow
        targets as edges — which is a different graph from the flow's own
        nodes (that one is ``FLOW_ILLEGAL_CYCLE``'s concern). Infinite
        recursion is the one failure in this phase that takes down more than a
        node, so it is caught before a flow can ever be published.

        ``seen`` also makes the walk terminate through a cycle that exists
        between *other* flows: not this author's problem, but it must not hang
        their publish.
        """
        origin = str(definition_id)
        seen: set[str] = set()
        frontier = list(flow_references(spec))

        while frontier:
            target = frontier.pop()
            if target == origin:
                return [
                    ValidationIssue(
                        FLOW_RUNFLOW_CYCLE,
                        f"Running flow '{target}' would come back to this flow; "
                        "a flow cannot run itself, directly or indirectly",
                    )
                ]
            if target in seen:
                continue
            seen.add(target)
            child = await self._load_reference_spec(target)
            if child is not None:
                frontier.extend(flow_references(child))
        return []

    async def _check_run_flow_targets(self, spec: FlowSpec) -> list[ValidationIssue]:
        """Each Run Flow target must be published and must not pause for a human.

        The child compiles with ``checkpointer=None`` — the parent owns
        persistence — so an ``interrupt()`` inside it has nowhere to write and
        would disappear without a trace. Langflow refuses the same shape for
        the same reason.
        """
        issues: list[ValidationIssue] = []
        for node in spec.nodes:
            if node.type != "RunFlow":
                continue
            target = str(node.values.get("flow_id", "") or "").strip()
            if not target:
                continue  # FLOW_RUNFLOW_MISSING_TARGET already reports this
            child = await self._load_reference_spec(target)
            if child is None:
                issues.append(
                    ValidationIssue(
                        FLOW_RUNFLOW_UNPUBLISHED,
                        f"RunFlow node '{node.id}' targets a flow with no published "
                        "version; publish that flow first",
                        node_id=node.id,
                    )
                )
                continue
            if any(child_node.type == "HumanInput" for child_node in child.nodes):
                issues.append(
                    ValidationIssue(
                        FLOW_RUNFLOW_HITL,
                        f"RunFlow node '{node.id}' targets a flow containing a Human "
                        "Input; a sub-flow cannot pause for a decision",
                        node_id=node.id,
                    )
                )
        return issues

    async def _check_resource_references(
        self, spec: FlowSpec, context: ResolverContext
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for node in spec.nodes:
            try:
                template = self._registry.get(node.type)
            except Exception:  # noqa: BLE001 - UnknownComponentError already reported elsewhere
                continue
            for field_name, field_def in template.inputs.items():
                if not field_def.options_source:
                    continue
                value = node.values.get(field_name, field_def.value)
                if not value:
                    continue  # a missing required value is FLOW_MISSING_INPUT's job

                # MULTISELECT fields (e.g. WebTools' `tools`) store a list of
                # ids, not one — checking the whole list as a single value
                # against resolve_options always fails, since str(["a", "b"])
                # is never a real option's value. Each item must be checked
                # on its own, and only the genuinely-missing ones reported.
                candidates = value if isinstance(value, list) else [value]
                missing = [
                    item
                    for item in candidates
                    if not await resource_exists(field_def.options_source, str(item), context)
                ]
                if missing:
                    shown = missing if isinstance(value, list) else missing[0]
                    issues.append(
                        ValidationIssue(
                            FLOW_UNKNOWN_RESOURCE,
                            f"Node '{node.id}' references '{shown}' via '{field_name}', "
                            "which no longer exists or isn't visible to you",
                            node_id=node.id,
                        )
                    )
        return issues

    # -- Migration on save (design spec 4.6) -----------------------------

    def migrate_flow(self, spec: FlowSpec) -> FlowSpec:
        """Rewrite every node's values to its template's current version.

        Applied on both sides of persistence: on save, so stored specs move
        forward, and on load, so a spec stored before a version bump never
        reaches the canvas or the compiler in its old shape.
        """
        return migrate_spec(spec, registry=self._registry)

    # -- Persistence ------------------------------------------------------

    async def save_flow(
        self,
        *,
        name: str,
        flow_spec: FlowSpec,
        existing_definition_id: UUID | None = None,
    ):
        """Migrate node values to current template versions, then persist.

        A flow-backed definition always has graph_schema="flow" — the schema
        that P2 dispatches to FlowAgent.
        """
        migrated = self.migrate_flow(flow_spec)
        payload = migrated.model_dump(by_alias=True, mode="json")
        flow_schema = GraphSchemaType.FLOW.value

        if existing_definition_id is not None:
            return await self._repository.update(
                existing_definition_id, {"flow_spec": payload, "graph_schema": flow_schema}
            )
        return await self._repository.create(name=name, graph_schema=flow_schema, flow_spec=payload)

    def load_flow(self, definition: Any) -> FlowSpec | None:
        """Parse a definition's stored flow_spec, or None if it has none."""
        if not definition or not definition.flow_spec:
            return None
        return FlowSpec.model_validate(definition.flow_spec)

    # -- Draft versioning (P3 Task 15) -------------------------------------
    #
    # save_flow/load_flow above are UNCHANGED by this addition — they still
    # read/write agent_definitions.flow_spec directly, exactly as P1 left
    # them. These new methods operate on agent_flow_versions instead, and are
    # deliberately independent until Task 16's publish transaction makes
    # flow_spec mean "denormalized cache of the published version" and
    # re-points the read side. Until then both paths are live at once — the
    # cost of never having a broken product at a task boundary.

    async def save_draft(
        self,
        *,
        definition_id: UUID,
        flow_spec: FlowSpec,
        user_id: str | None = None,
    ) -> Any:
        """Migrate template values to current versions, then upsert the
        one mutable draft row for this definition. Never touches
        agent_definitions.flow_spec."""
        migrated = self.migrate_flow(flow_spec)
        payload = migrated.model_dump(by_alias=True, mode="json")
        return await self._version_repository.upsert_draft(
            definition_id, payload, created_by=user_id
        )

    async def load_draft(self, definition_id: UUID) -> FlowSpec | None:
        """The current draft for a definition, or None if it has never
        been edited via the draft path.

        Migrated on read: a draft stored before a template version bump would
        otherwise reach the canvas in its old shape and be rendered against
        the current template — the `Loop` -> `While` rename leaves orphaned
        handles that way — and the next autosave would persist that.
        """
        draft = await self._version_repository.get_draft(definition_id)
        if draft is None:
            return None
        return self.migrate_flow(FlowSpec.model_validate(draft.flow_spec))

    async def discard_draft(self, definition_id: UUID) -> bool:
        """Drop the working draft. Returns False when there was none."""
        return await self._version_repository.delete_draft(definition_id)

    async def load_published(self, definition_id: UUID) -> FlowSpec | None:
        """The currently published flow for a definition — what chat and
        Playground actually execute — or None if nothing has been
        published yet."""
        published = await self._version_repository.get_published(definition_id)
        if published is None:
            return None
        return self.migrate_flow(FlowSpec.model_validate(published.flow_spec))

    async def list_versions(self, definition_id: UUID) -> list[Any]:
        """Every version row for a definition, newest first."""
        return await self._version_repository.list_versions(definition_id)

    async def load_version(self, definition_id: UUID, version_no: int) -> Any | None:
        """One version row (metadata + its flow_spec), or None if absent.

        Powers the canvas version preview and JSON export (Task 45) — the
        spec is returned exactly as stored, with no template migration or
        re-validation: a historical version must preview as the artifact it
        was when published, not as today's defaults would render it.
        """
        return await self._version_repository.get_by_version_no(definition_id, version_no)

    # -- Publish (P3 Task 16) ----------------------------------------------

    async def publish_flow(
        self,
        *,
        definition_id: UUID,
        published_by: str,
        context: ResolverContext,
        expected_version_no: int | None = None,
        notes: str | None = None,
    ) -> Any:
        """Validate the current draft, then publish it atomically.

        A flow must never become production-visible without passing the
        same structural + resource-existence checks /validate-flow already
        enforces pre-flight — this task does not trust the client validated
        before calling publish. Cache invalidation happens only after
        publish_draft's transaction has committed (never inside it): a
        rolled-back publish must not have evicted a valid cached graph.
        """
        draft = await self._version_repository.get_draft(definition_id)
        if draft is None:
            raise FlowVersionConflictError(
                f"No draft exists for definition '{definition_id}' to publish"
            )

        draft_spec = FlowSpec.model_validate(draft.flow_spec)
        validation = await self.validate_flow(draft_spec, context, definition_id=definition_id)
        if not validation.valid:
            raise FlowValidationError(validation.errors)

        published = await self._version_repository.publish_draft(
            definition_id,
            published_by=published_by,
            expected_version_no=expected_version_no,
            notes=notes,
        )

        from agents.agent_factory import invalidate_agent_cache_for

        invalidate_agent_cache_for(str(definition_id), "flow")

        return published

    # -- Rollback (P3 Task 17) ----------------------------------------------

    async def rollback_flow(
        self,
        *,
        definition_id: UUID,
        target_version_no: int,
        published_by: str,
    ) -> Any:
        """Restore a previously published version as a new version.

        No re-validation here: the target version already passed
        publish_flow's validation when it was first published, and its
        flow_spec is copied verbatim (design spec 5.3) — there is nothing
        new to validate. Cache invalidation follows the same
        after-commit-only rule as publish_flow.
        """
        restored = await self._version_repository.rollback_to(
            definition_id,
            target_version_no=target_version_no,
            published_by=published_by,
        )

        from agents.agent_factory import invalidate_agent_cache_for

        invalidate_agent_cache_for(str(definition_id), "flow")

        return restored
