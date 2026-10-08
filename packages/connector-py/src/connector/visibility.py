"""Runtime-controlled connector visibility.

The registry never hard-codes which connectors are exposed. Instead it asks a
:class:`VisibilityPolicy`, which combines one or more
:class:`VisibilitySource` objects. Sources are consulted **on every decision**,
so a change in an environment variable, a config file or an admin API call
takes effect without restarting the service.

Precedence (first source with an opinion wins):

    RuntimeOverrides  >  FileVisibilitySource  >  EnvVisibilitySource  >  defaults

Rules understood by every source::

    {
      "default": "enabled" | "disabled",        # fallback when nothing matches
      "enabled":  ["postgres", "http_json"],     # explicit allow (supports fnmatch "*")
      "disabled": ["postgres"],                  # explicit deny  (wins over enabled)
      "tags": {"enabled": ["db"], "disabled": ["experimental"]}
    }
"""

from __future__ import annotations

import fnmatch
import json
import os
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from .extras import require_extra
from .models import ConnectorDefinition

Decision = Literal["enabled", "disabled"]


@dataclass(frozen=True)
class Verdict:
    """Outcome of a visibility check."""

    visible: bool
    reason: str | None = None
    source: str | None = None

    @staticmethod
    def allow(source: str | None = None) -> Verdict:
        return Verdict(True, None, source)

    @staticmethod
    def deny(reason: str, source: str | None = None) -> Verdict:
        return Verdict(False, reason, source)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class TagRules(BaseModel):
    enabled: list[str] = Field(default_factory=list)
    disabled: list[str] = Field(default_factory=list)


class VisibilityRules(BaseModel):
    """Declarative rule set. Empty rules have no opinion."""

    default: Decision | None = None
    enabled: list[str] = Field(default_factory=list)
    disabled: list[str] = Field(default_factory=list)
    tags: TagRules = Field(default_factory=TagRules)

    def is_empty(self) -> bool:
        return (
            self.default is None
            and not self.enabled
            and not self.disabled
            and not self.tags.enabled
            and not self.tags.disabled
        )

    def decide(self, definition: ConnectorDefinition) -> Decision | None:
        """Return a decision or ``None`` if the rules say nothing about it."""
        name = definition.name
        if _matches(name, self.disabled):
            return "disabled"
        if definition.tags & set(self.tags.disabled):
            return "disabled"
        if _matches(name, self.enabled):
            return "enabled"
        if definition.tags & set(self.tags.enabled):
            return "enabled"
        return self.default


def _matches(name: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, p) for p in patterns)


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


@runtime_checkable
class VisibilitySource(Protocol):
    """Anything that can produce :class:`VisibilityRules` at decision time."""

    @property
    def source_name(self) -> str: ...

    def rules(self) -> VisibilityRules: ...


class StaticVisibilitySource:
    """Fixed rules supplied in code (useful for defaults and tests)."""

    def __init__(self, rules: VisibilityRules | Mapping[str, Any], name: str = "static") -> None:
        self._rules = rules if isinstance(rules, VisibilityRules) else VisibilityRules(**rules)
        self._name = name

    @property
    def source_name(self) -> str:
        return self._name

    def rules(self) -> VisibilityRules:
        return self._rules


class EnvVisibilitySource:
    """Rules from environment variables, re-read on every call.

    ``CONNECTOR_ENABLED="postgres,http_*"``, ``CONNECTOR_DISABLED="jsonl_file"``,
    ``CONNECTOR_DEFAULT="disabled"``, ``CONNECTOR_TAGS_DISABLED="experimental"``.
    """

    def __init__(
        self, prefix: str = "CONNECTOR_", environ: Mapping[str, str] | None = None
    ) -> None:
        self._prefix = prefix
        self._environ = environ

    @property
    def source_name(self) -> str:
        return "env"

    def rules(self) -> VisibilityRules:
        env = self._environ if self._environ is not None else os.environ
        p = self._prefix
        default = env.get(f"{p}DEFAULT", "").strip().lower() or None
        if default not in (None, "enabled", "disabled"):
            default = None
        return VisibilityRules(
            default=default,  # type: ignore[arg-type]
            enabled=_split(env.get(f"{p}ENABLED")),
            disabled=_split(env.get(f"{p}DISABLED")),
            tags=TagRules(
                enabled=_split(env.get(f"{p}TAGS_ENABLED")),
                disabled=_split(env.get(f"{p}TAGS_DISABLED")),
            ),
        )


def _split(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


class FileVisibilitySource:
    """Rules from a JSON (or YAML, if ``pyyaml`` is installed) file.

    The file is re-parsed only when its mtime changes, so editing it at runtime
    is both cheap and immediately effective. A missing file yields empty rules.
    Optionally point at a nested key with ``key="connectors.visibility"``.
    """

    def __init__(self, path: str | os.PathLike[str], key: str | None = None) -> None:
        self._path = Path(path)
        self._key = key
        self._mtime: float | None = None
        self._cached = VisibilityRules()
        self._lock = threading.Lock()

    @property
    def source_name(self) -> str:
        return f"file:{self._path}"

    def rules(self) -> VisibilityRules:
        with self._lock:
            try:
                mtime = self._path.stat().st_mtime
            except FileNotFoundError:
                self._mtime = None
                self._cached = VisibilityRules()
                return self._cached
            if mtime != self._mtime:
                self._cached = self._load()
                self._mtime = mtime
            return self._cached

    def _load(self) -> VisibilityRules:
        text = self._path.read_text(encoding="utf-8")
        if self._path.suffix.lower() in {".yaml", ".yml"}:
            yaml = require_extra("yaml", extra="yaml", feature="a YAML visibility file")
            data = yaml.safe_load(text) or {}
        else:
            data = json.loads(text or "{}")
        if self._key:
            for part in self._key.split("."):
                data = data.get(part, {}) if isinstance(data, dict) else {}
        return VisibilityRules(**(data or {}))


class CallableVisibilitySource:
    """Adapter for any callable returning rules (e.g. a DB lookup)."""

    def __init__(
        self, fn: Callable[[], VisibilityRules | Mapping[str, Any]], name: str = "callable"
    ) -> None:
        self._fn = fn
        self._name = name

    @property
    def source_name(self) -> str:
        return self._name

    def rules(self) -> VisibilityRules:
        r = self._fn()
        return r if isinstance(r, VisibilityRules) else VisibilityRules(**r)


class RuntimeOverrides:
    """In-memory, thread-safe overrides mutated by an admin API at runtime."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Decision] = {}

    @property
    def source_name(self) -> str:
        return "runtime"

    def set_enabled(self, name: str, enabled: bool) -> None:
        with self._lock:
            self._state[name] = "enabled" if enabled else "disabled"

    def clear(self, name: str | None = None) -> None:
        with self._lock:
            if name is None:
                self._state.clear()
            else:
                self._state.pop(name, None)

    def snapshot(self) -> dict[str, Decision]:
        with self._lock:
            return dict(self._state)

    def rules(self) -> VisibilityRules:
        with self._lock:
            return VisibilityRules(
                enabled=[n for n, d in self._state.items() if d == "enabled"],
                disabled=[n for n, d in self._state.items() if d == "disabled"],
            )


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


class VisibilityPolicy(Protocol):
    def evaluate(self, definition: ConnectorDefinition) -> Verdict: ...


@dataclass
class LayeredVisibilityPolicy:
    """Consults sources in order; the first with an opinion decides.

    With no opinion anywhere the connector is visible (``default_visible``).
    """

    sources: list[VisibilitySource] = field(default_factory=list)
    default_visible: bool = True

    def evaluate(self, definition: ConnectorDefinition) -> Verdict:
        for source in self.sources:
            decision = source.rules().decide(definition)
            if decision == "enabled":
                return Verdict.allow(source.source_name)
            if decision == "disabled":
                return Verdict.deny(f"disabled by {source.source_name}", source.source_name)
        if self.default_visible:
            return Verdict.allow("default")
        return Verdict.deny("hidden by default", "default")

    def add_source(self, source: VisibilitySource, *, first: bool = False) -> None:
        if first:
            self.sources.insert(0, source)
        else:
            self.sources.append(source)


class AllowAllPolicy:
    def evaluate(self, definition: ConnectorDefinition) -> Verdict:
        return Verdict.allow("allow-all")


def default_policy(
    *,
    overrides: RuntimeOverrides | None = None,
    config_file: str | os.PathLike[str] | None = None,
    config_key: str | None = None,
    env_prefix: str = "CONNECTOR_",
    defaults: VisibilityRules | Mapping[str, Any] | None = None,
) -> LayeredVisibilityPolicy:
    """Build the conventional stack: overrides > file > env > static defaults."""
    sources: list[VisibilitySource] = []
    if overrides is not None:
        sources.append(overrides)
    if config_file is not None:
        sources.append(FileVisibilitySource(config_file, key=config_key))
    sources.append(EnvVisibilitySource(prefix=env_prefix))
    if defaults is not None:
        sources.append(StaticVisibilitySource(defaults, name="defaults"))
    return LayeredVisibilityPolicy(sources=sources)
