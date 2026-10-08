"""Template migration registry.

Guarantees a component template change can never break a saved flow. A
migration transforms one node's ``values`` dict forward by exactly one
template version; ``migrate_node_values`` chains them from an old version to
the current one.

Migrations run **on read** — in the compiler (P2) and the editor load path —
and specs are rewritten to the current version on the next save (Task 6),
never silently on read. Additive field changes need no migration; renames and
removals do.

See ``.tmp/flow-canvas-design.md`` section 4.6.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from core.exceptions import MissingMigrationError, UnknownComponentError


class ComponentRegistryLike(Protocol):
    def get(self, component_type: str) -> Any: ...


if TYPE_CHECKING:
    from schemas.flows import FlowSpec

MigrationFn = Callable[[dict[str, Any]], dict[str, Any]]

_SKIP_TYPES = ("note", "noteNode")


_registry_provider: Callable[[], ComponentRegistryLike] | None = None


def set_registry_provider(provider: Callable[[], ComponentRegistryLike]) -> None:
    """Register a provider for the component registry to decouple migrations from registry."""
    global _registry_provider
    _registry_provider = provider


def _resolve_registry(registry: ComponentRegistryLike | None = None) -> ComponentRegistryLike:
    if registry is not None:
        return registry
    if _registry_provider is not None:
        return _registry_provider()
    raise RuntimeError("No ComponentRegistry provider registered for migrations")


_migrations: dict[tuple[str, int], MigrationFn] = {}

# (old_type, at_version) -> new_type. Applied by ``migrate_spec`` before value
# migrations: when a component is renamed (its function changed enough that the
# name-function bond demands a new name), a stored node keeps working by being
# rewritten to the new type at that type's version 1. The classic value
# migration registry only moves a *type's* values forward, never its name.
_type_renames: dict[tuple[str, int], str] = {}

# (type, at_version) -> {old_handle: new_handle}. Applied by ``migrate_spec``
# to the edges touching a node of that type, alongside its value migration.
_handle_renames: dict[tuple[str, int], dict[str, str]] = {}


def register_migration(component_type: str, from_version: int, fn: MigrationFn) -> None:
    """Register a migration transforming values at ``from_version`` to ``from_version + 1``."""
    _migrations[(component_type, from_version)] = fn


def register_type_rename(old_type: str, at_version: int, new_type: str) -> None:
    """Register that ``old_type`` at ``at_version`` should be read as ``new_type``."""
    _type_renames[(old_type, at_version)] = new_type


def register_handle_rename(component_type: str, at_version: int, old_handle: str, new_handle: str) -> None:
    """Register that ``old_handle`` on ``component_type`` at ``at_version`` is
    read as ``new_handle``, rewriting the edges of every stored node of it.

    The value registry moves a type's *values* forward and ``_type_renames``
    moves its *name*; neither can follow a **port** whose name changed, and a
    stale handle does not error — it silently detaches the branch.
    """
    _handle_renames.setdefault((component_type, at_version), {})[old_handle] = new_handle


def migrate_node_values(
    component_type: str,
    from_version: int,
    to_version: int,
    values: dict[str, Any],
    *,
    registry: ComponentRegistryLike | None = None,
) -> dict[str, Any]:
    """Migrate one node's values from ``from_version`` to ``to_version``.

    Chains registered migrations in order. Never mutates ``values`` — the
    caller's dict, which may be a cached config, is always left untouched.

    Raises:
        UnknownComponentError: ``component_type`` is not registered.
        ValueError: ``to_version < from_version`` — migrations only move forward.
        MissingMigrationError: no migration is registered to advance past some
            version in the requested range.
    """
    reg = _resolve_registry(registry)
    reg.get(component_type)  # raises UnknownComponentError

    if to_version < from_version:
        raise ValueError(f"cannot migrate {component_type!r} backward from version {from_version} to {to_version}")

    current = dict(values)
    version = from_version
    while version < to_version:
        fn = _migrations.get((component_type, version))
        if fn is None:
            raise MissingMigrationError(component_type, version)
        current = fn(current)
        version += 1
    return current


def migrate_spec(spec: FlowSpec, *, registry: ComponentRegistryLike | None = None) -> FlowSpec:
    """Return ``spec`` with every node's values at its template's current version.

    The doctrine (design spec 4.6): migrations run **on read** — the compiler
    and the editor load path both call this — and the next save rewrites the
    stored spec. A node whose type is not registered, or is a canvas note, is
    left untouched for the validator to report.
    """
    reg = _resolve_registry(registry)
    migrated_nodes = []
    # node id -> {old_handle: new_handle}, collected while the nodes are still
    # at their stored version, applied to the edges once the walk is done.
    edge_renames: dict[str, dict[str, str]] = {}
    changed = False
    for node in spec.nodes:
        if node.type in _SKIP_TYPES:
            migrated_nodes.append(node)
            continue

        handle_map = _handle_renames.get((node.type, node.template_version))
        if handle_map:
            edge_renames[node.id] = handle_map

        renamed_to = _type_renames.get((node.type, node.template_version))
        if renamed_to is not None:
            node = node.model_copy(update={"type": renamed_to, "template_version": 1})
            changed = True
            try:
                new_template = reg.get(renamed_to)
            except UnknownComponentError:
                new_template = None
            if new_template is not None:
                # A type rename carries the *old* type's value dict onto the
                # new type. Fill in every field the new template declares but
                # the old values are missing, so the new node's runtime never
                # hits a ``None`` where its schema promised a default — e.g. a
                # v1 `Loop` -> `While` node had no `max_iterations` and 500'd
                # the run (B14).
                hydrated = {name: field.value for name, field in new_template.inputs.items() if field.value is not None}
                hydrated.update(node.values or {})
                node = node.model_copy(update={"values": hydrated})

        try:
            template = reg.get(node.type)
        except UnknownComponentError:
            migrated_nodes.append(node)
            continue
        if node.template_version == template.template_version:
            migrated_nodes.append(node)
            continue
        new_values = migrate_node_values(
            node.type,
            node.template_version,
            template.template_version,
            node.values,
            registry=reg,
        )
        migrated_nodes.append(
            node.model_copy(
                update={
                    "values": new_values,
                    "template_version": template.template_version,
                }
            )
        )
        changed = True
    migrated_edges = spec.edges
    if edge_renames:
        migrated_edges = []
        for edge in spec.edges:
            src = edge_renames.get(edge.source, {}).get(edge.source_handle)
            tgt = edge_renames.get(edge.target, {}).get(edge.target_handle)
            if src is None and tgt is None:
                migrated_edges.append(edge)
                continue
            migrated_edges.append(
                edge.model_copy(
                    update={
                        "source_handle": src or edge.source_handle,
                        "target_handle": tgt or edge.target_handle,
                    }
                )
            )
            changed = True

    if not changed:
        return spec
    return spec.model_copy(update={"nodes": migrated_nodes, "edges": migrated_edges})
