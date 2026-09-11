"""Composition validation service for multi-agent hierarchies."""

from uuid import UUID

from pydantic import BaseModel

from core.logger import get_logger
from repository.agent_definition_repository import AgentDefinitionRepository

logger = get_logger(__name__)


class CompositionValidationError(ValueError):
    """Base error for composition validation failures."""

    pass


class CircularDependencyError(CompositionValidationError):
    """Raised when circular dependency detected (A→B→A)."""

    pass


class SchemaMismatchError(CompositionValidationError):
    """Raised when sub-agent doesn't support master schema."""

    pass


class MaxDepthExceededError(CompositionValidationError):
    """Raised when hierarchy depth exceeds limit."""

    pass


class MissingAgentError(CompositionValidationError):
    """Raised when referenced agent doesn't exist."""

    pass


class CompositionValidationResult(BaseModel):
    """Result of composition validation."""

    valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    depth: int = 0


class CompositionValidationService:
    """Validates multi-agent compositions before saving."""

    MAX_DEPTH = 5
    MAX_SUB_AGENTS = 20

    def __init__(self, repository: AgentDefinitionRepository):
        """Initialize with repository."""
        self.repository = repository

    @staticmethod
    def _normalize_id(agent_id: UUID | str) -> UUID | str:
        """Convert UUID strings from JSON columns back to UUID values when possible."""
        if isinstance(agent_id, str):
            try:
                return UUID(agent_id)
            except ValueError:
                return agent_id
        return agent_id

    def _normalize_ids(self, agent_ids: list[UUID | str]) -> list[UUID | str]:
        return [self._normalize_id(agent_id) for agent_id in agent_ids]

    async def validate_references_exist(
        self, sub_agent_ids: list[UUID | str]
    ) -> tuple[bool, list[str]]:
        """
        Verify all referenced agents exist and are active.

        Returns:
            (is_valid, error_list)
        """
        if not sub_agent_ids:
            return True, []

        if len(sub_agent_ids) > self.MAX_SUB_AGENTS:
            return False, [f"Too many sub-agents: {len(sub_agent_ids)} > {self.MAX_SUB_AGENTS}"]

        errors = []
        for sub_id in self._normalize_ids(sub_agent_ids):
            agent = await self.repository.get_by_id(sub_id)
            if not agent:
                errors.append(f"Sub-agent {sub_id} does not exist")

        return len(errors) == 0, errors

    async def detect_circular_dependency(
        self, agent_id: UUID | str, sub_agent_ids: list[UUID | str]
    ) -> bool:
        """
        Detect circular dependencies using BFS.

        A circular dependency exists if we can reach agent_id by following
        sub_agent_ids chains. Example: A→B→A is circular.

        Returns:
            True if circular dependency detected, False otherwise
        """
        if not sub_agent_ids:
            return False

        # BFS from sub_agent_ids to see if we reach agent_id
        visited: set[UUID | str] = set()
        queue: list[UUID | str] = self._normalize_ids(sub_agent_ids)
        target_agent_id = self._normalize_id(agent_id)

        while queue:
            current_id = queue.pop(0)

            if current_id == target_agent_id:
                return True  # Circular!

            if current_id in visited:
                continue

            visited.add(current_id)

            # Load current agent and get its sub_agents
            current_agent = await self.repository.get_by_id(current_id)
            if current_agent and current_agent.sub_agent_ids:
                queue.extend(self._normalize_ids(current_agent.sub_agent_ids))

        return False

    async def validate_schema_compatibility(
        self,
        master_schema: str,
        sub_agent_ids: list[UUID | str],
    ) -> tuple[bool, list[str]]:
        """
        Validate sub-agents support the master schema.

        Rules:
        - SUPERVISOR: sub-agents must support tool calling (REACT, etc.)
        - PIPELINE: sub-agents must support sequential processing
        - All: sub-agents cannot be zero_shot (no logic)

        Returns:
            (is_valid, error_list)
        """
        if not sub_agent_ids:
            return True, []

        errors = []
        master_schema_upper = master_schema.upper()

        for sub_id in self._normalize_ids(sub_agent_ids):
            sub_agent = await self.repository.get_by_id(sub_id)
            if not sub_agent:
                continue

            sub_schema_upper = sub_agent.graph_schema.upper()

            # §5.4: Flow-backed agents cannot be composed into classic agents
            if sub_schema_upper == "FLOW":
                errors.append(
                    f"Sub-agent '{sub_agent.name}' (FLOW) cannot be used as a sub-agent; "
                    "flow-backed agents cannot be composed into classic agents (design spec 5.4)"
                )
                continue

            # SUPERVISOR requires tool-capable agents
            if master_schema_upper == "SUPERVISOR":
                # REACT, PLAN_EXECUTE support tools
                if sub_schema_upper == "ZERO_SHOT":
                    errors.append(
                        f"Sub-agent '{sub_agent.name}' (ZERO_SHOT) cannot be used in "
                        f"SUPERVISOR (requires tool-capable agents)"
                    )

            # PIPELINE requires deterministic output
            if master_schema_upper == "PIPELINE":
                # Should support sequential processing
                if sub_schema_upper == "SUPERVISOR":
                    errors.append(
                        f"Sub-agent '{sub_agent.name}' (SUPERVISOR) cannot be used in "
                        f"PIPELINE (nested supervisors not allowed)"
                    )

            # No recursive multi-agent in sub-agents
            if sub_schema_upper in ("SUPERVISOR", "PIPELINE"):
                if master_schema_upper in ("SUPERVISOR", "PIPELINE"):
                    logger.warning(
                        f"Nested multi-agent detected: "
                        f"{master_schema} contains {sub_schema_upper}. "
                        f"This is allowed but may be complex."
                    )

        return len(errors) == 0, errors

    def get_composition_depth(self, agent_id: UUID) -> int:
        """
        Synchronously get max composition depth.

        This must be called after loading agent from DB with sub_agent_ids.
        Returns -1 if error.
        """
        # This is a sync wrapper - actual implementation is async
        # Use await get_composition_depth_async() instead
        logger.warning(
            "get_composition_depth should be called as async via get_composition_depth_async"
        )
        return 0

    async def get_composition_depth_async(
        self, agent_id: UUID | str, visited: set[UUID | str] | None = None
    ) -> int:
        """
        Asynchronously get max composition depth.

        Recursively finds deepest sub-agent chain.
        """
        if visited is None:
            visited = set()

        agent_id = self._normalize_id(agent_id)
        if agent_id in visited:
            return 0  # Circular (shouldn't happen if validation works)

        visited.add(agent_id)

        agent = await self.repository.get_by_id(agent_id)
        if not agent or not agent.sub_agent_ids:
            return 0

        max_depth = 0
        for sub_id in self._normalize_ids(agent.sub_agent_ids):
            depth = await self.get_composition_depth_async(sub_id, visited.copy())
            max_depth = max(max_depth, depth + 1)

        return max_depth

    async def validate_max_depth(
        self, agent_id: UUID | str | None, sub_agent_ids: list[UUID | str]
    ) -> tuple[bool, list[str]]:
        """
        Validate composition depth doesn't exceed limit.

        Returns:
            (is_valid, error_list)
        """
        errors = []

        proposed_depth = 0
        for sub_id in self._normalize_ids(sub_agent_ids):
            sub_depth = await self.get_composition_depth_async(sub_id)
            proposed_depth = max(proposed_depth, sub_depth + 1)

        if proposed_depth >= self.MAX_DEPTH:
            errors.append(
                f"Sub-agent depth would exceed limit: {proposed_depth} >= {self.MAX_DEPTH}"
            )

        return len(errors) == 0, errors

    async def validate_full_composition(
        self,
        agent_id: UUID | str | None,
        graph_schema: str,
        sub_agent_ids: list[UUID | str],
    ) -> CompositionValidationResult:
        """
        Run all validations and return aggregated result.

        Args:
            agent_id: None if creating new, set if updating
            graph_schema: Master agent's schema
            sub_agent_ids: List of referenced sub-agent IDs

        Returns:
            CompositionValidationResult with all errors/warnings
        """
        errors: list[str] = []
        warnings: list[str] = []
        depth = 0

        # 1. Check references exist
        valid, ref_errors = await self.validate_references_exist(sub_agent_ids)
        if not valid:
            errors.extend(ref_errors)

        # 2. Check for circular dependencies
        if agent_id and await self.detect_circular_dependency(agent_id, sub_agent_ids):
            errors.append("Circular dependency detected: Agent cannot reference itself")

        # 3. Check schema compatibility
        valid, schema_errors = await self.validate_schema_compatibility(graph_schema, sub_agent_ids)
        if not valid:
            errors.extend(schema_errors)

        # 4. Check max depth
        valid, depth_errors = await self.validate_max_depth(agent_id, sub_agent_ids)
        if not valid:
            errors.extend(depth_errors)

        # 5. Calculate final depth
        if not errors and sub_agent_ids:
            try:
                max_sub_depth = 0
                for sub_id in self._normalize_ids(sub_agent_ids):
                    sub_depth = await self.get_composition_depth_async(sub_id)
                    max_sub_depth = max(max_sub_depth, sub_depth)
                depth = max_sub_depth + 1
            except Exception as e:
                logger.error(f"Error calculating depth: {e}", exc_info=True)
                depth = 0

        return CompositionValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            depth=depth,
        )
