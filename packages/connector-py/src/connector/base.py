"""Abstract connector contracts.

Class hierarchy (interface segregation):

* :class:`BaseConnector` – identity, spec and connectivity check. Everything a
  catalog needs, nothing about data movement.
* :class:`BaseSource` – adds ``discover`` and ``read``.
* :class:`BaseDestination` – adds ``write`` (and optional ``begin``/``finalize``
  hooks for per-sync bookkeeping such as overwrite semantics).

A concrete connector only has to declare a pydantic ``Config`` model, a
``definition`` and implement the abstract methods. The JSON Schema spec, config
validation and secret masking are derived automatically.

Config secrets: mark a field with :func:`secret_field` and it is flagged as
``writeOnly`` / ``x-secret`` in the spec so UIs can render a password input and
services can mask it when echoing a stored config. A mapping that holds
credentials next to ordinary settings (request headers, driver options) is
declared with :func:`sensitive_mapping_field`: its keys stay readable and what
a key named like a credential holds is masked.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator, Mapping
from copy import deepcopy
from importlib.resources import files
from typing import Any, ClassVar, Generic, Self, TypeVar, get_args, get_origin

from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo

from .errors import ConfigValidationError
from .models import (
    Batch,
    Catalog,
    CheckResult,
    ConfiguredCatalog,
    ConnectorDefinition,
    ConnectorKind,
    ConnectorSpec,
    DestinationSyncMode,
    Record,
    State,
    SyncMode,
    SyncState,
    WriteResult,
)
from .redaction import mask_sensitive_values, redact_secrets, sensitive_values

ConfigT = TypeVar("ConfigT", bound=BaseModel)

SECRET_KEY = "x-secret"
SENSITIVE_KEYS_KEY = "x-sensitive-keys"

# Per-class results of what does not change while the process runs: the bundled icon
# (a package resource) and the JSON schema of the ``Config`` model. A catalog request
# asks every registered class for both.
_ICON_CACHE: dict[type, str | None] = {}
_SCHEMA_CACHE: dict[type, dict[str, Any]] = {}


def clear_class_caches() -> None:
    """Forget cached icons and schemas (tests that swap resources or models)."""
    _ICON_CACHE.clear()
    _SCHEMA_CACHE.clear()


def secret_field(**kwargs: Any) -> Any:
    """Declare a config field as a secret. Thin wrapper over ``pydantic.Field``."""
    from pydantic import Field

    extra = dict(kwargs.pop("json_schema_extra", None) or {})
    extra[SECRET_KEY] = True
    extra["writeOnly"] = True
    return Field(json_schema_extra=extra, **kwargs)


def sensitive_mapping_field(**kwargs: Any) -> Any:
    """Declare a mapping field whose keys may name credentials (``headers``, ``params``).

    The field is flagged ``x-sensitive-keys`` in the spec. Its keys are shown;
    what a key named like a credential holds is masked like a secret field (see
    :func:`connector.redaction.is_sensitive_key`).
    """
    from pydantic import Field

    extra = dict(kwargs.pop("json_schema_extra", None) or {})
    extra[SENSITIVE_KEYS_KEY] = True
    return Field(json_schema_extra=extra, **kwargs)


def _is_flagged(field: FieldInfo, flag: str) -> bool:
    extra = field.json_schema_extra
    return isinstance(extra, dict) and bool(extra.get(flag))


class EmptyConfig(BaseModel):
    """Default config for connectors that need no parameters."""


def _read_icon(ref: str | None) -> str | None:
    if not ref:
        return None
    package, _, resource = ref.rpartition(":")
    package = package or "connector.icons"
    try:
        return files(package).joinpath(resource).read_text(encoding="utf-8")
    except (ModuleNotFoundError, FileNotFoundError, OSError, TypeError):
        return None


def _config_parameter(cls: type) -> type[BaseModel] | None:
    """The model a connector class is parameterised with (``BaseSource[Model]``), if any.

    The nearest parameterisation in the MRO decides; one that still names a type
    variable (a generic base such as ``RestSource[ConfigT]``) leaves it open.
    """
    for klass in cls.__mro__:
        for base in klass.__dict__.get("__orig_bases__", ()):
            origin = get_origin(base)
            if not (isinstance(origin, type) and issubclass(origin, BaseConnector)):
                continue
            for arg in get_args(base):
                if isinstance(arg, type) and issubclass(arg, BaseModel):
                    return arg
            return None
    return None


class BaseConnector(abc.ABC, Generic[ConfigT]):
    """Common behaviour for sources and destinations.

    Subclasses must set the class attribute ``definition`` and name their
    configuration model, as the type parameter (``BaseSource[MyConfig]``), as
    ``Config = MyConfig``, or both. Where both are given they must agree: the
    parameter is what the code is type-checked against, ``Config`` is what
    validates a configuration at run time. ``Config`` may be the declared model
    or a model derived from it.
    Instances are cheap; construct one per configured use (``from_config``).
    """

    definition: ClassVar[ConnectorDefinition]
    Config: ClassVar[type[BaseModel]] = EmptyConfig

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        declared = _config_parameter(cls)
        # A model derived from the declared one agrees with it: whatever the class and
        # its parents do with the declared model holds for the narrower one as well.
        if declared is None or issubclass(cls.Config, declared):
            return
        if "Config" in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} is parameterised with {declared.__name__} "
                f"but sets Config = {cls.Config.__name__}"
            )
        cls.Config = declared

    def __init__(self, config: ConfigT) -> None:
        self.config: ConfigT = config

    # ---- identity ---------------------------------------------------------

    @classmethod
    def name(cls) -> str:
        return cls.definition.name

    @classmethod
    def kind(cls) -> ConnectorKind:
        return cls.definition.kind

    # ---- spec / config ----------------------------------------------------

    @classmethod
    def spec(cls) -> ConnectorSpec:
        """JSON Schema spec generated from the ``Config`` model (generated once per class;
        the caller gets its own copy)."""
        schema = _SCHEMA_CACHE.get(cls)
        if schema is None:
            schema = _SCHEMA_CACHE[cls] = cls.Config.model_json_schema()
        return ConnectorSpec(
            name=cls.definition.name,
            display_name=cls.definition.display_name,
            kind=cls.definition.kind,
            connection_specification=deepcopy(schema),
            documentation_url=cls.definition.documentation_url,
            category=cls.definition.category,
            icon_svg=cls.icon_svg(),
            supported_sync_modes=cls.supported_sync_modes(),
            supported_destination_sync_modes=cls.supported_destination_sync_modes(),
        )

    @classmethod
    def icon_svg(cls) -> str | None:
        """Return the bundled SVG markup for this connector, or ``None``.

        Resolution of ``definition.icon``:
        * ``"name.svg"``            -> resource inside ``connector.icons``
        * ``"pkg.module:name.svg"`` -> resource inside that package (third-party connectors)

        Read once per class. Override for dynamic icons. Missing resources yield
        ``None`` rather than raising.
        """
        if cls in _ICON_CACHE:
            return _ICON_CACHE[cls]
        svg = _ICON_CACHE[cls] = _read_icon(cls.definition.icon)
        return svg

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return []

    @classmethod
    def supported_destination_sync_modes(cls) -> list[DestinationSyncMode]:
        return []

    @classmethod
    def validate_config(cls, raw: Mapping[str, Any]) -> ConfigT:
        try:
            return cls.Config.model_validate(dict(raw))  # type: ignore[return-value]
        except ValidationError as exc:
            # Location and message only. pydantic reports the failing input too, and
            # for a model-level validator that is the whole configuration, secrets
            # included; the same goes for the original exception's own text.
            errors = exc.errors(include_input=False, include_url=False, include_context=False)
            raise ConfigValidationError(cls.definition.name, errors) from None

    @classmethod
    def from_config(cls, raw: Mapping[str, Any]) -> Self:
        return cls(cls.validate_config(raw))

    @classmethod
    def secret_fields(cls) -> frozenset[str]:
        return frozenset(
            n for n, f in cls.Config.model_fields.items() if _is_flagged(f, SECRET_KEY)
        )

    @classmethod
    def sensitive_mapping_fields(cls) -> frozenset[str]:
        """The mapping fields declared with :func:`sensitive_mapping_field`."""
        return frozenset(
            n for n, f in cls.Config.model_fields.items() if _is_flagged(f, SENSITIVE_KEYS_KEY)
        )

    @classmethod
    def mask_config(cls, raw: Mapping[str, Any], mask: str = "********") -> dict[str, Any]:
        """Return a copy of ``raw`` with secret values replaced by ``mask``.

        Those are the secret fields and, inside a sensitive mapping field,
        whatever a key named like a credential holds.
        """
        secrets = cls.secret_fields()
        mappings = cls.sensitive_mapping_fields()
        masked: dict[str, Any] = {}
        for key, value in raw.items():
            if key in secrets:
                masked[key] = mask if value not in (None, "") else value
            elif key in mappings:
                masked[key] = mask_sensitive_values(value, mask)
            else:
                masked[key] = value
        return masked

    def secret_values(self) -> list[str]:
        """The secrets this connector was configured with, for redacting text about it."""
        values = [getattr(self.config, name, None) for name in sorted(self.secret_fields())]
        for name in sorted(self.sensitive_mapping_fields()):
            values.extend(sensitive_values(getattr(self.config, name, None)))
        return [value for value in values if isinstance(value, str) and value]

    # ---- lifecycle --------------------------------------------------------

    @abc.abstractmethod
    async def check(self) -> CheckResult:
        """Verify the configuration can reach the external system."""

    async def check_connection(self) -> CheckResult:
        """:meth:`check` for callers that want an answer, never an exception.

        Connectors report the failures they expect as ``CheckResult(ok=False)``;
        whatever else goes wrong (a missing driver, a bug) ends up here. The
        message is shown to people who may not see the configuration: the
        configured secrets and the query strings of quoted addresses are masked.
        """
        try:
            result = await self.check()
        except Exception as exc:  # noqa: BLE001 - the verdict is the result
            result = CheckResult(ok=False, message=f"{type(exc).__name__}: {exc}")
        if result.message:
            result = result.model_copy(update={"message": self.redacted(result.message)})
        return result

    def redacted(self, text: str) -> str:
        """``text`` without this connector's secrets, URL passwords and query strings."""
        return redact_secrets(text, self.secret_values())

    async def close(self) -> None:
        """Release pooled resources. Default: nothing to do."""

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


class BaseSource(BaseConnector[ConfigT]):
    """A connector that produces records."""

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH]

    @abc.abstractmethod
    async def discover(self) -> Catalog:
        """List the streams this configured source can read."""

    @abc.abstractmethod
    def read(
        self,
        catalog: ConfiguredCatalog,
        state: SyncState | None = None,
    ) -> AsyncIterator[Record | State]:
        """Yield :class:`Record` items and, optionally, :class:`State` checkpoints.

        A ``State`` item tells the runner "everything for this stream up to
        here is durable"; the runner flushes the destination before storing
        it. Sources that do not support incremental sync never yield ``State``.
        """

    async def preview(self, stream: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return up to ``limit`` sample rows of ``stream``. Default: read and stop."""
        catalog = await self.discover()
        target = catalog.get(stream)
        if target is None:
            from .errors import StreamNotFoundError

            raise StreamNotFoundError(stream)
        configured = ConfiguredCatalog.from_catalog(catalog, only=[stream])
        rows: list[dict[str, Any]] = []
        items = self.read(configured)
        try:
            async for item in items:
                if isinstance(item, Record):
                    rows.append(item.data)
                    if len(rows) >= limit:
                        break
        finally:
            # Stopping early leaves the stream open. Its cleanup (a cursor, a scroll)
            # belongs here, while the source is still open, not to the garbage collector.
            aclose = getattr(items, "aclose", None)
            if aclose is not None:
                await aclose()
        return rows


class BaseDestination(BaseConnector[ConfigT]):
    """A connector that consumes batches of records.

    One sync run calls ``begin``, then ``write`` per batch, then exactly one of
    ``finalize`` (every batch was written) or ``abort`` (the run stopped early).
    ``job_id`` is the same in all of them and in ``Batch.job_id``.
    """

    needs_final_batch: ClassVar[bool] = False
    """Send a closing ``is_last`` batch for every stream, even when it is empty.
    For destinations whose receiving end waits for an end-of-stream marker."""

    @classmethod
    def supported_destination_sync_modes(cls) -> list[DestinationSyncMode]:
        return [DestinationSyncMode.OVERWRITE, DestinationSyncMode.APPEND]

    async def begin(
        self,
        catalog: ConfiguredCatalog,
        connection_id: str | None = None,
        *,
        job_id: str | None = None,
    ) -> None:
        """Called once before the first batch of a sync."""

    @abc.abstractmethod
    async def write(self, batch: Batch) -> WriteResult:
        """Persist one batch. Must be idempotent per ``(job_id, stream, batch_index)``
        where possible: the runner retries a failed write.

        Raise :class:`~connector.errors.DestinationWriteError` to stop the run
        without retries.
        """

    async def finalize(
        self,
        catalog: ConfiguredCatalog,
        connection_id: str | None = None,
        *,
        job_id: str | None = None,
    ) -> None:
        """Called once after the last batch (also on empty syncs)."""

    async def abort(
        self,
        catalog: ConfiguredCatalog,
        connection_id: str | None = None,
        *,
        job_id: str | None = None,
        error: BaseException | None = None,
    ) -> None:
        """Called instead of ``finalize`` when the run failed, timed out, was cancelled or
        was interrupted by a shutdown after ``begin``.

        For releasing what the run still holds open (an upload, a transaction that
        was never acknowledged). It must not discard batches ``write`` acknowledged:
        their checkpoints were stored while the run progressed, and the next run
        continues after them. An exception raised here is logged and does not replace
        the original failure."""
