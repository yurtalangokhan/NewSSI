"""
Pydantic request / response models.

All Pydantic models used across the service routes are
collected here to avoid circular imports and duplication.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

__all__ = [
    "AssistantSearchRequest",
    "AssistantCreateRequest",
    "AssistantUpdateRequest",
    "ThreadSearchRequest",
    "ThreadCreateRequest",
    "ThreadUpdateRequest",
    "ThreadState",
    "ThreadHistoryRequest",
    "RunCreate",
    "RunCancel",
]


# =============================================================================
# Assistant models
# =============================================================================

class AssistantSearchRequest(BaseModel):
    """Request model for assistant search."""
    limit: int = 100
    offset: int = 0
    metadata: Optional[Dict] = None
    graph_id: Optional[str] = None


class AssistantCreateRequest(BaseModel):
    """Request model for creating an assistant."""
    graph_id: str
    name: Optional[str] = None
    config: Optional[Dict] = None
    metadata: Optional[Dict] = None


class AssistantUpdateRequest(BaseModel):
    """Request model for updating an assistant."""
    name: Optional[str] = None
    config: Optional[Dict] = None
    metadata: Optional[Dict] = None


# =============================================================================
# Thread models
# =============================================================================

class ThreadSearchRequest(BaseModel):
    limit: int = 100
    offset: int = 0
    metadata: Optional[Dict] = None


class ThreadCreateRequest(BaseModel):
    thread_id: Optional[str] = None
    metadata: Optional[Dict] = None


class ThreadUpdateRequest(BaseModel):
    metadata: Optional[Dict] = None


class ThreadState(BaseModel):
    values: Dict[str, Any]
    next: List[str]
    checkpoint: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    parent_config: Optional[Dict[str, Any]] = None
    parent_checkpoint: Optional[Dict[str, Any]] = None  # For SDK compatibility


class ThreadHistoryRequest(BaseModel):
    limit: int = 10
    before: Optional[str] = None
    metadata: Optional[Dict] = None
    checkpoint: Optional[Dict] = None


# =============================================================================
# Run models
# =============================================================================

class RunCreate(BaseModel):
    """Request model for creating a run."""
    assistant_id: str
    input: Optional[Dict[str, Any]] = None
    command: Optional[Dict[str, Any]] = None  # SDK sends {resume: value} for interrupt resumption
    config: Optional[Dict[str, Any]] = None
    stream_mode: Optional[List[str]] = ["values"]
    interrupt_before: Optional[List[str]] = None
    interrupt_after: Optional[List[str]] = None
    webhook: Optional[str] = None
    checkpoint: Optional[Dict[str, Any]] = None
    checkpoint_id: Optional[str] = None
    multitask_strategy: Optional[str] = None
    on_completion: Optional[str] = None
    on_disconnect: Optional[str] = None
    after_seconds: Optional[int] = None


class RunCancel(BaseModel):
    """Request model for cancelling a run."""
    wait: bool = False
    action: Optional[str] = "interrupt"  # "interrupt" or "rollback"
