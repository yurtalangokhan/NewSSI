"""Domain exceptions.

Services and domain modules raise these; only routes translate them to HTTP
statuses. Never raise ``HTTPException`` below the route layer.

Note: exceptions predating this module still live beside their callers
(``GraphBuilderError``, ``CompositionValidationError`` and friends).
Consolidating them is deliberately out of scope for the flow-canvas work.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from error_contract import (
    ApplicationError,
    BadRequestError,
    ConflictError,
    DependencyUnavailableError,
    ForbiddenError,
    NotFoundError,
    RateLimitedError,
    UnauthorizedError,
    ValidationFailedError,
)

if TYPE_CHECKING:
    from domain.flows.validator import ValidationIssue


class FlowError(Exception):
    """Base class for agent flow canvas errors."""


class DuplicateComponentError(FlowError):
    """A component type was registered twice."""

    def __init__(self, component_type: str):
        self.component_type = component_type
        super().__init__(f"Component type {component_type!r} is already registered")


class UnknownComponentError(FlowError):
    """A flow references a component type that is not in the registry."""

    def __init__(self, component_type: str):
        self.component_type = component_type
        super().__init__(f"Unknown component type: {component_type!r}")


class UnknownOptionsSourceError(FlowError):
    """A template names an options_source key that has no registered resolver."""

    def __init__(self, source: str):
        self.source = source
        super().__init__(f"Unknown options source: {source!r}")


class NotAResourceNodeError(FlowError):
    """resolve_resources() was handed an execution-kind node.

    partition_nodes() should already have kept executions out of the resource
    list; reaching this means that contract was violated somewhere upstream.
    """

    def __init__(self, node_id: str, component_type: str):
        self.node_id = node_id
        self.component_type = component_type
        super().__init__(f"Node {node_id!r} (type {component_type!r}) is not a resource node")


class FlowBuildError(FlowError):
    """A FlowSpec could not be compiled into a runnable graph.

    FlowGraphBuilder assumes its input already passed FlowService.validate_flow
    (P1 Task 6); a spec that reaches here in a state validation should have
    caught (e.g. no ChatInput) still fails clearly rather than misbehaving
    silently.
    """


class FlowVersionConflictError(FlowError):
    """A publish/rollback could not proceed as requested.

    Covers both: no draft exists to publish, and a concurrent publish won
    the race for the next version_no (P3 Task 16, design spec 10). The route
    translates this to 409 so the UI can offer reload-and-retry.
    """


class FlowValidationError(FlowError):
    """A flow failed structural/resource validation at the point it was
    about to become production-visible (publish, rollback).

    Carries the same ValidationIssue list /validate-flow already returns, so
    the route can serialize a publish-time rejection identically to a
    pre-flight validation failure.
    """

    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        super().__init__(f"Flow failed validation with {len(issues)} error(s)")


class FlowNotPublishedError(FlowError):
    """A flow-backed agent was asked to chat before anything was published.

    Distinct from FlowBuildError: nothing is broken, the flow simply has no
    published version yet. Routes map this to 409 so the client can tell
    "publish it first" apart from "it failed to compile".
    """

    def __init__(self, persona_id: int):
        self.persona_id = persona_id
        super().__init__(f"Flow for persona '{persona_id}' has no published version yet")


class MissingMigrationError(FlowError):
    """No migration is registered to advance a component past a given version.

    A template version bump without a matching migration would silently break
    every flow still holding values at the old version.
    """

    def __init__(self, component_type: str, from_version: int):
        self.component_type = component_type
        self.from_version = from_version
        super().__init__(
            f"No migration registered for {component_type!r} from version "
            f"{from_version}. Register one with "
            f"register_migration({component_type!r}, {from_version}, ...)."
        )


__all__ = [
    "ApplicationError",
    "BadRequestError",
    "ConflictError",
    "DependencyUnavailableError",
    "DuplicateComponentError",
    "FlowBuildError",
    "FlowError",
    "FlowNotPublishedError",
    "FlowValidationError",
    "FlowVersionConflictError",
    "ForbiddenError",
    "MissingMigrationError",
    "NotAResourceNodeError",
    "NotFoundError",
    "RateLimitedError",
    "UnauthorizedError",
    "UnknownComponentError",
    "UnknownOptionsSourceError",
    "ValidationFailedError",
]
