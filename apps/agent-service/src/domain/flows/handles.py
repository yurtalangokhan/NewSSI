"""Values-aware view of a component template.

Two questions the validator and the canvas must answer *identically*:

- which output handles does this node actually have, given its values?
- is this field visible, given its sibling values?

Both are declared on the template (``Handle.expands_from``,
``InputField.show_when``) rather than special-cased per component type, so a
new component that needs either costs no code here and none in the canvas.

Pure and total, like ``handle_types.py``: no I/O, one answer per input, never
raises. A hand-edited spec is untrusted input, not a crash.
"""

from __future__ import annotations

from typing import Any

from models.flows import ComponentTemplate, Handle, InputField, ShowWhen


def resolved_values(template: ComponentTemplate, values: dict[str, Any]) -> dict[str, Any]:
    """Node values with every unset field filled from its template default.

    Visibility must be judged against what the node *effectively* holds: a
    field left untouched still has the template's default, and a rule keyed
    on it would otherwise read ``None``.
    """
    merged: dict[str, Any] = {name: f.value for name, f in template.inputs.items()}
    merged.update(values or {})
    return merged


def _rule_holds(rule: ShowWhen | None, resolved: dict[str, Any]) -> bool:
    """Whether a ShowWhen rule is satisfied by the resolved sibling values.
    No rule -> always true; every clause that is set must hold."""
    if rule is None:
        return True
    actual = resolved.get(rule.field)
    if rule.equals is not None and actual != rule.equals:
        return False
    if rule.not_equals is not None and actual == rule.not_equals:
        return False
    if rule.one_of is not None and actual not in rule.one_of:
        return False
    if rule.not_one_of is not None and actual in rule.not_one_of:
        return False
    return True


def _row_label(row: Any, label_key: str) -> str | None:
    """The branch label a table row selects, or None when it has none."""
    if isinstance(row, str):
        return row
    if isinstance(row, dict):
        value = row.get(label_key)
        if isinstance(value, str):
            return value
    return None


def effective_output_handles(template: ComponentTemplate, values: dict[str, Any]) -> list[Handle]:
    """The output handles a node really has, expanding declared dynamic ones.

    A handle carrying ``expands_from`` becomes one handle per row of that
    field. Rows without a usable label are skipped; when no row yields one the
    declared handle is kept, so a freshly dropped node still has something to
    wire.
    """
    resolved = resolved_values(template, values)
    result: list[Handle] = []
    for handle in template.handles.outputs:
        if not _rule_holds(handle.show_when, resolved):
            continue  # a conditional port switched off by a sibling field
        if handle.expands_from is None or handle.expands_label_key is None:
            result.append(handle)
            continue
        rows = resolved.get(handle.expands_from)
        labels: list[str] = []
        if isinstance(rows, list):
            for row in rows:
                label = _row_label(row, handle.expands_label_key)
                if label and label.strip():
                    labels.append(label)
        if not labels:
            result.append(handle)
            continue
        result.extend(Handle(name=label, types=handle.types) for label in labels)
    return result


def effective_input_handles(template: ComponentTemplate, values: dict[str, Any]) -> list[Handle]:
    """The input handles a node really has, given its values.

    The mirror of ``effective_output_handles``. No component expands an input
    from a table today, so this only applies ``show_when``; keeping the same
    shape means a future expanding input costs nothing here — and, more
    importantly, gives the canvas one function to mirror instead of a direct
    read of ``template.handles.inputs`` that would drift the moment a port
    became conditional.
    """
    resolved = resolved_values(template, values)
    return [h for h in template.handles.inputs if _rule_holds(h.show_when, resolved)]


def field_visible(field: InputField, resolved: dict[str, Any]) -> bool:
    """Whether ``field`` should be shown, given its siblings' resolved values.

    Callers pass the output of ``resolved_values``. A field with no
    ``show_when`` is always visible; every clause that is set must hold.
    """
    return _rule_holds(field.show_when, resolved)


def visible_inputs(template: ComponentTemplate, values: dict[str, Any]) -> dict[str, InputField]:
    """The template's fields that are visible for these values, in order."""
    resolved = resolved_values(template, values)
    return {
        name: field for name, field in template.inputs.items() if field_visible(field, resolved)
    }
