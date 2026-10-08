"""Template rendering without attribute or index traversal.

str.format lets a template walk attributes from any value it is given:
{x.__init__.__globals__[os].environ} reads the process environment. This
formatter resolves only top-level names and stringifies every value.
"""

from __future__ import annotations

from string import Formatter
from typing import Any

from error_contract import UnsafeTemplateError

MAX_FORMAT_WIDTH = 4096


class _SafeFormatter(Formatter):
    def get_field(self, field_name: str, args: Any, kwargs: Any) -> tuple[Any, str]:
        if "." in field_name or "[" in field_name:
            raise UnsafeTemplateError("Attribute and index access are not allowed in templates")
        return self.get_value(field_name, args, kwargs), field_name

    def get_value(self, key: Any, args: Any, kwargs: Any) -> Any:  # noqa: ARG002
        if isinstance(key, int):
            raise UnsafeTemplateError("Positional fields are not allowed")
        # A plain KeyError, not a fallback to "": PromptTemplate's own
        # caller (flow_builder._make_prompt_template_node) turns this into
        # a descriptive "not present in scratch" error, which is more
        # useful for debugging a misconfigured flow than a silent empty
        # substitution would be.
        return kwargs[key]

    def format_field(self, value: Any, format_spec: str) -> str:
        digits = "".join(ch for ch in format_spec if ch.isdigit())
        if digits and int(digits) > MAX_FORMAT_WIDTH:
            raise UnsafeTemplateError("Format width is too large")
        return format(str(value), format_spec)


_FORMATTER = _SafeFormatter()


def validate_template(template: str) -> None:
    """Raise UnsafeTemplateError if template contains attribute access,
    index access, a positional field, or an oversized format spec --
    without needing the substitution values safe_format itself requires.
    Used by the flow validator to reject an unsafe template at save time,
    before it can ever reach safe_format with real scratch values.
    """
    try:
        fields = list(Formatter().parse(template))
    except ValueError as exc:
        raise UnsafeTemplateError(f"Malformed template: {exc}") from exc

    for _literal, field_name, format_spec, _conversion in fields:
        if field_name is None:
            continue
        if "." in field_name or "[" in field_name:
            raise UnsafeTemplateError("Attribute and index access are not allowed in templates")
        if field_name.isdigit() or field_name == "":
            raise UnsafeTemplateError("Positional fields are not allowed")
        digits = "".join(ch for ch in (format_spec or "") if ch.isdigit())
        if digits and int(digits) > MAX_FORMAT_WIDTH:
            raise UnsafeTemplateError("Format width is too large")


def safe_format(template: str, values: dict[str, Any]) -> str:
    """Render template, substituting only top-level {name} placeholders.

    Raises UnsafeTemplateError for attribute access ({x.y}), index access
    ({x[0]}), positional fields ({0}), or an oversized format spec, and
    KeyError for a name not present in values -- the same contract
    str.format(**values) had, minus the traversal it also allowed.
    """
    return _FORMATTER.vformat(template, (), dict(values or {}))
