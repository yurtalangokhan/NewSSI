from __future__ import annotations

from typing import Any

from ..domain.component_catalog import ComponentKind, get_component
from ..domain.definitions import AgentDefinition
from ..domain.errors import (
    IncompatibleComponentError,
    MaxDepthError,
    MissingRequiredNestedError,
    MissingRequiredSettingError,
    NestedCycleError,
    SecretInConfigError,
    UnavailableComponentError,
    UnknownComponentKeyError,
    ValidationIssue,
)

MAX_NESTED_DEPTH = 5

_SECRET_HINTS = ("api_key", "token", "secret", "password", "credential")

_SETTING_TYPES = {
    "array": (list, tuple),
    "boolean": (bool,),
    "integer": (int,),
    "number": (int, float),
    "object": (dict,),
    "string": (str,),
}


def _scan_secrets(settings: dict[str, Any], path: str, issues: list[ValidationIssue]) -> None:
    for key, value in settings.items():
        if isinstance(key, str) and any(hint in key.lower() for hint in _SECRET_HINTS):
            issues.append(
                ValidationIssue(
                    code=SecretInConfigError.code,
                    message=f"Secret-like key '{key}' found in {path}.",
                    context={"key": key, "path": path},
                )
            )
        elif isinstance(value, dict):
            _scan_secrets(value, f"{path}.{key}", issues)


class ValidateAgentDefinition:
    """Framework-free validation of an ``AgentDefinition`` aggregate.

    Returns typed ``ValidationIssue`` values and can raise ``CompositionError``
    subclasses carrying stable codes for hard failures.
    """

    def selected_keys(self, definition: AgentDefinition) -> set[str]:
        keys: set[str] = set()
        if definition.brain is not None:
            keys.add(definition.brain.key)
        keys.update(p.key for p in definition.perceptrons)
        if definition.graph is not None:
            keys.add(definition.graph.key)
        return keys

    def validate(self, definition: AgentDefinition) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []
        selected = self.selected_keys(definition)

        if definition.brain is not None:
            self._check_component(
                definition.brain.key,
                ComponentKind.BRAIN,
                definition.brain.settings,
                selected,
                issues,
            )
        for perceptron in definition.perceptrons:
            self._check_component(
                perceptron.key, ComponentKind.PERCEPTRON, perceptron.settings, selected, issues
            )
        if definition.graph is not None:
            self._check_component(
                definition.graph.key,
                ComponentKind.GRAPH_STRATEGY,
                definition.graph.settings,
                selected,
                issues,
            )
            descriptor = get_component(definition.graph.key)
            if descriptor is not None and descriptor.required_nested and not definition.nested:
                issues.append(
                    ValidationIssue(
                        code=MissingRequiredNestedError.code,
                        message=f"Graph strategy '{descriptor.key}' requires nested definitions.",
                        context={"key": descriptor.key},
                    )
                )

        for policy_settings in (
            definition.runtime_policy.memory,
            definition.runtime_policy.safety,
            definition.runtime_policy.retry,
            definition.runtime_policy.limits,
        ):
            _scan_secrets(policy_settings, "runtime_policy", issues)
        if definition.brain is not None:
            _scan_secrets(definition.brain.settings, "brain", issues)

        self._check_cycles(definition, [], issues)
        self._check_depth(definition, 0, issues)
        return tuple(issues)

    def _check_component(
        self,
        key: str,
        kind: ComponentKind,
        settings: dict[str, Any],
        selected: set[str],
        issues: list[ValidationIssue],
    ) -> None:
        descriptor = get_component(key)
        if descriptor is None:
            issues.append(
                ValidationIssue(
                    code=UnknownComponentKeyError.code,
                    message=f"Unknown {kind.value} key '{key}'.",
                    context={"key": key, "kind": kind.value},
                )
            )
            return
        if not descriptor.available:
            issues.append(
                ValidationIssue(
                    code=UnavailableComponentError.code,
                    message=f"Component '{key}' is not available.",
                    context={"key": key, "kind": kind.value},
                )
            )
            return
        for required in descriptor.required_settings:
            if required not in settings:
                issues.append(
                    ValidationIssue(
                        code=MissingRequiredSettingError.code,
                        message=f"Component '{key}' requires setting '{required}'.",
                        context={"key": key, "setting": required},
                    )
                )
        for name, expected_type in (descriptor.settings_schema or {}).items():
            if name in settings and not isinstance(settings[name], _SETTING_TYPES[expected_type]):
                issues.append(
                    ValidationIssue(
                        code=MissingRequiredSettingError.code,
                        message=f"Component '{key}' setting '{name}' must be {expected_type}.",
                        context={"key": key, "setting": name, "type": expected_type},
                    )
                )
        for other in descriptor.incompatible_with:
            if other in selected:
                issues.append(
                    ValidationIssue(
                        code=IncompatibleComponentError.code,
                        message=f"Component '{key}' is incompatible with '{other}'.",
                        context={"key": key, "other": other},
                    )
                )

    def _check_cycles(
        self, definition: AgentDefinition, path: list[str], issues: list[ValidationIssue]
    ) -> None:
        if definition.identity in path:
            issues.append(
                ValidationIssue(
                    code=NestedCycleError.code,
                    message=f"Nested composition cycle detected at '{definition.identity}'.",
                    context={"cycle": [*path, definition.identity]},
                )
            )
            return
        for child in definition.nested:
            self._check_cycles(child, [*path, definition.identity], issues)

    def _check_depth(
        self, definition: AgentDefinition, depth: int, issues: list[ValidationIssue]
    ) -> None:
        if depth > MAX_NESTED_DEPTH:
            issues.append(
                ValidationIssue(
                    code=MaxDepthError.code,
                    message=f"Nested depth {depth} exceeds maximum {MAX_NESTED_DEPTH}.",
                    context={"depth": depth},
                )
            )
            return
        for child in definition.nested:
            self._check_depth(child, depth + 1, issues)

    def validate_or_raise(self, definition: AgentDefinition) -> None:
        issues = self.validate(definition)
        for issue in issues:
            if issue.code == UnknownComponentKeyError.code:
                raise UnknownComponentKeyError(issue.message, details=issue.context)
            if issue.code == UnavailableComponentError.code:
                raise UnavailableComponentError(issue.message, details=issue.context)
            if issue.code == MissingRequiredNestedError.code:
                raise MissingRequiredNestedError(issue.message, details=issue.context)
            if issue.code == NestedCycleError.code:
                raise NestedCycleError(issue.message, details=issue.context)
            if issue.code == MaxDepthError.code:
                raise MaxDepthError(issue.message, details=issue.context)
            if issue.code == SecretInConfigError.code:
                raise SecretInConfigError(issue.message, details=issue.context)
            if issue.code == IncompatibleComponentError.code:
                raise IncompatibleComponentError(issue.message, details=issue.context)
            if issue.code == MissingRequiredSettingError.code:
                raise MissingRequiredSettingError(issue.message, details=issue.context)
        return None
