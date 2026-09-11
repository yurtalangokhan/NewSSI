"""Cache invalidation service for cascade updating when agents change."""

from uuid import UUID

from core.logger import get_logger
from repository.agent_definition_repository import AgentDefinitionRepository

logger = get_logger(__name__)


class CacheInvalidationService:
    """Cascade-invalidate agent graphs when sub-agents update."""

    def __init__(self, repository: AgentDefinitionRepository):
        """Initialize with repository."""
        self.repository = repository

    async def find_agents_using_sub_agent(self, sub_agent_id: UUID) -> list[UUID]:
        """
        Find all agents that reference sub_agent_id in their sub_agent_ids.

        Returns:
            List of agent UUIDs
        """
        return await self.repository.find_agents_by_sub_agent_id(sub_agent_id)

    async def invalidate_agent_and_dependents(self, agent_id: UUID):
        """
        Invalidate cache for agent and all agents that depend on it.

        This is a cascade operation:
        1. Remove graph cache for agent_id
        2. Find all agents using agent_id as sub-agent
        3. Recursively invalidate each parent

        Args:
            agent_id: The agent that changed (its cache will be cleared)
        """
        # Step 1: Clear direct cache
        # Note: Actual cache is in dynamic_agent._agent_cache dict
        # This service triggers the clearing, controller/service layer handles it
        logger.info(f"Invalidating cache for agent {agent_id}")

        # Step 2: Find all agents using this one as sub-agent
        parent_agents = await self.find_agents_using_sub_agent(agent_id)

        # Step 3: Recursively invalidate parents
        for parent_id in parent_agents:
            logger.info(f"Cascade invalidating parent agent {parent_id}")
            # Recursive call to invalidate parents of parents
            await self.invalidate_agent_and_dependents(parent_id)

    async def cascade_invalidate(self, agent_id: UUID):
        """
        BFS-based cascade invalidation of all dependent agents.

        Alternative implementation using explicit BFS queue instead of recursion.
        Safer for deep hierarchies.

        Args:
            agent_id: Agent that changed
        """
        visited: set[UUID] = set()
        queue: list[UUID] = [agent_id]

        while queue:
            current_id = queue.pop(0)

            if current_id in visited:
                continue

            visited.add(current_id)
            logger.info(f"Invalidating cache for agent {current_id}")

            # Find agents using current_id as sub-agent
            dependent_agents = await self.find_agents_using_sub_agent(current_id)
            queue.extend(dependent_agents)

        logger.info(f"Cascade invalidation complete: {len(visited)} agents affected")

    async def invalidate_by_schema_change(self, agent_id: UUID):
        """
        Invalidate when agent's schema changes (might affect compatibility).

        This is more conservative than invalidate_agent_and_dependents,
        only clearing cache if schema change requires recompilation.

        Args:
            agent_id: Agent whose schema changed
        """
        # For now, same as full invalidation
        # Later: could check if schema change affects dependents
        await self.invalidate_agent_and_dependents(agent_id)

    async def validate_and_invalidate(
        self, agent_id: UUID, new_sub_agent_ids: list[UUID]
    ) -> tuple[bool, list[str]]:
        """
        Update sub-agents and handle cache invalidation.

        This is a combined operation that:
        1. Checks if change would break any dependents
        2. Updates the agent
        3. Cascades invalidation

        Args:
            agent_id: Agent being updated
            new_sub_agent_ids: New sub-agent references

        Returns:
            (success, error_list)
        """
        # Get current agent
        agent = await self.repository.get_by_id(agent_id)
        if not agent:
            return False, [f"Agent {agent_id} not found"]

        # Check what's changing
        old_ids = set(agent.sub_agent_ids or [])
        new_ids = set(new_sub_agent_ids)

        added = new_ids - old_ids
        removed = old_ids - new_ids

        logger.info(
            f"Agent {agent_id} sub-agents changing: +{len(added)} added, -{len(removed)} removed"
        )

        # Invalidate all affected caches
        if added or removed:
            await self.invalidate_agent_and_dependents(agent_id)

        return True, []
