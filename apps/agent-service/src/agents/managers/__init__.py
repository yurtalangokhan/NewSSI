"""Manager implementations."""

from agents.base.manager import (
    AgentManager,
    DelegateRequest,
    HierarchicalManager,
    PipelineManager,
    SupervisorManager,
    TaskResult,
)
from agents.managers.pipeline import DynamicPipelineSupervisor, get_pipeline
from agents.managers.supervisor import DynamicFlatSupervisor, get_supervisor

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
