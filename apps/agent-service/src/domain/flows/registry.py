from __future__ import annotations

import builtins
from collections import defaultdict
from collections.abc import Callable, Iterator

from core.exceptions import UnknownComponentError
from models.flows import ComponentTemplate, Lifecycle


class ComponentRegistry:
    """Process-wide registry of component templates."""

    def __init__(self) -> None:
        self._templates: dict[str, ComponentTemplate] = {}

    def register(self, template: ComponentTemplate) -> None:
        """Register a component template, raising ValueError on collision."""
        if template.type in self._templates:
            raise ValueError(f"Component type {template.type!r} is already registered")
        self._templates[template.type] = template

    def get(self, component_type: str) -> ComponentTemplate:
        """Return a template by type, deprecated ones included."""
        try:
            return self._templates[component_type]
        except KeyError:
            raise UnknownComponentError(component_type) from None

    def list(self, *, include_deprecated: bool = False) -> builtins.list[ComponentTemplate]:
        """Return all registered templates, in registration order."""
        return [
            t
            for t in self._templates.values()
            if t.lifecycle is not Lifecycle.DEPRECATED or include_deprecated
        ]

    def list_grouped(
        self, *, include_deprecated: bool = False
    ) -> dict[str, builtins.list[ComponentTemplate]]:
        """Return templates grouped by category, in registration order."""
        grouped: dict[str, builtins.list[ComponentTemplate]] = defaultdict(builtins.list)
        for template in self._templates.values():
            if template.lifecycle is Lifecycle.DEPRECATED and not include_deprecated:
                continue
            grouped[template.category].append(template)
        return dict(grouped)


_registry: ComponentRegistry | None = None


def _iter_template_registrars() -> Iterator[Callable[[ComponentRegistry], None]]:
    """Yield each template pack's registrar, in catalog order.

    Adding a template module is one entry here — no edit to ``get_registry``.
    Imports stay lazy so importing this module doesn't pull the whole
    template tree.
    """
    from domain.flows.templates.agents_multi import register_multi_agent_templates
    from domain.flows.templates.core import register_core_templates
    from domain.flows.templates.datasources import register_datasource_templates
    from domain.flows.templates.mcp import register_mcp_templates
    from domain.flows.templates.memory import register_memory_templates
    from domain.flows.templates.processing import register_processing_templates
    from domain.flows.templates.rag import register_rag_templates
    from domain.flows.templates.web import register_web_templates

    yield register_core_templates
    yield register_mcp_templates
    yield register_memory_templates
    yield register_processing_templates
    yield register_multi_agent_templates
    yield register_rag_templates
    yield register_web_templates
    yield register_datasource_templates


def get_registry() -> ComponentRegistry:
    """Return the process-wide registry, populating it on first use.

    First use also registers the template migrations (see
    ``templates/migrations_core``): a template that declares a
    ``template_version > 1`` needs its migration path present whenever the
    real registry is in play, and this is the single bootstrap point.
    """
    global _registry
    if _registry is None:
        _registry = ComponentRegistry()
        for register in _iter_template_registrars():
            register(_registry)
        from domain.flows.templates.migrations_core import register_core_migrations

        register_core_migrations()
    return _registry
