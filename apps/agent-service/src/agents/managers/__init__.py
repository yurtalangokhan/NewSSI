"""Manager implementations."""

from agents.base.manager import (
    AgentManager,
    SupervisorManager,
    PipelineManager,
    HierarchicalManager,
    TaskResult,
    DelegateRequest,
)
from agents.managers.supervisor import DynamicFlatSupervisor, get_supervisor
from agents.managers.pipeline import DynamicPipelineSupervisor, get_pipeline

__all__ = [
    "AgentManager",
    "SupervisorManager",
    "PipelineManager",
    "HierarchicalManager",
    "TaskResult",
    "DelegateRequest",
    "DynamicFlatSupervisor",
    "get_supervisor",
    "DynamicPipelineSupervisor",
    "get_pipeline",
]
