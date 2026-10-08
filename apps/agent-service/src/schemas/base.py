"""Base Schema Model for agent-service schemas.

Provides strongly typed Pydantic V2 models with transparent dictionary-like
mapping semantics for 100% backward compatibility with legacy callers.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class BaseSchemaModel(BaseModel):
    """Base class for domain and API schema models.

    Combines Pydantic v2 validation and typed field access with mapping
    operations, allowing callers to migrate smoothly from untyped dicts to typed
    schema models without breaking legacy dict access.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True, from_attributes=True)

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item) from None

    def __setitem__(self, item: str, value: Any) -> None:
        setattr(self, item, value)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self):
        return iter(self.model_fields)

    def keys(self):
        return self.model_fields.keys()

    def items(self):
        return [(k, getattr(self, k)) for k in self.model_fields]

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


# Backward compatibility alias
BaseDomainEntity = BaseSchemaModel
