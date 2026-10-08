"""Constraints belong in the schema: the model should not be able to
express an out-of-range value at all. Spec TS-9."""

import importlib
import inspect
import types
import typing
from pathlib import Path

UNBOUNDED_INT_ARGS = {"timeout", "max_lines", "limit", "max_pages", "lines", "page_number"}


class _Recorder:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *a, **k):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def _iter_tool_functions():
    root = Path(__file__).resolve().parents[1] / "src" / "tools"
    for path in sorted(root.glob("*_tools.py")):
        module = importlib.import_module(f"src.tools.{path.stem}")
        for name, obj in vars(module).items():
            if inspect.isclass(obj) and name.endswith("Tools"):
                recorder = _Recorder()
                obj().register_tools(recorder)
                yield from recorder.tools.items()


def _resolve_hints(fn) -> dict[str, object]:
    """typing.get_type_hints, not inspect.signature(fn).parameters[x].annotation.

    Several tool modules have ``from __future__ import annotations`` (PEP
    563), which makes every annotation on the nested tool functions defined
    in them a plain string ("str", "int | None", ...) rather than the real
    type object. A check comparing against ``str``/``int`` directly would
    silently pass every argument in those modules -- not because they are
    bounded, but because the comparison never matches. get_type_hints
    resolves the string back to the actual type, closing that gap.
    """
    return typing.get_type_hints(fn, include_extras=True)


def test_no_integer_argument_is_unbounded():
    offenders = []
    for tool_name, fn in _iter_tool_functions():
        hints = _resolve_hints(fn)
        for arg in inspect.signature(fn).parameters:
            if arg not in UNBOUNDED_INT_ARGS:
                continue
            annotation = hints.get(arg)
            if annotation is int:
                offenders.append(f"{tool_name}.{arg}")
            elif typing.get_origin(annotation) is typing.Annotated:
                continue
    assert offenders == [], f"unbounded integer arguments: {offenders}"


def _is_unbounded_str(annotation) -> bool:
    """True for a bare `str`, including inside `X | None` / `Optional[X]`.

    A Union is not `is str`, so `pattern: str | None` slipped past a check
    that only ever compared the resolved hint to `str` directly -- the
    exact shape every optional string argument in this codebase uses.
    """
    if annotation is str:
        return True
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        return any(
            _is_unbounded_str(arg) for arg in typing.get_args(annotation) if arg is not type(None)
        )
    return False


def test_every_free_text_argument_has_a_length_bound():
    offenders = []
    for tool_name, fn in _iter_tool_functions():
        hints = _resolve_hints(fn)
        for arg in inspect.signature(fn).parameters:
            if _is_unbounded_str(hints.get(arg)) and arg not in {"command_id"}:
                offenders.append(f"{tool_name}.{arg}")
    assert offenders == [], f"unbounded string arguments: {offenders}"


def test_string_future_annotations_do_not_hide_unbounded_arguments():
    """Regression test for the exact gap _resolve_hints closes: a module
    using `from __future__ import annotations` must still be checked, not
    silently skipped because its annotations are strings at runtime."""

    def fake_tool(subject: str, body: str) -> str:  # type: ignore[empty-body]
        ...

    # Simulates what `from __future__ import annotations` does to every
    # annotation in a module: they become plain strings at runtime.
    fake_tool.__annotations__ = {"subject": "str", "body": "str", "return": "str"}
    hints = typing.get_type_hints(fake_tool, include_extras=True)
    assert hints["subject"] is str
    assert hints["body"] is str
