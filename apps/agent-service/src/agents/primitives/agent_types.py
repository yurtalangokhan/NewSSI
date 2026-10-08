"""Type definitions for agents."""

from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import Pregel

from agents.primitives.base import LazyLoadingAgent

AgentGraph = CompiledStateGraph | Pregel
AgentGraphLike = CompiledStateGraph | Pregel | LazyLoadingAgent
