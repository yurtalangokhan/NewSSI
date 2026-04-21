"""Knowledge tool selector.

Maps rag_config keys to the appropriate retrieval tools.
Single responsibility: decides WHICH tools to include, not how to use them.
"""

from langchain_core.tools import BaseTool


class KnowledgeToolSelector:
    """Selects retrieval tools based on the keys present in rag_config."""

    @staticmethod
    def select_tools(rag_config: dict) -> list[BaseTool]:
        """Return the tools appropriate for the given rag_config.

        - document_processing collections → database_search (PGVector)
        - knowledge_graph collections     → graph_search (Neo4j hybrid)
        """
        from agents.tools import database_search, graph_search

        tools: list[BaseTool] = []
        if rag_config.get("document_processing"):
            tools.append(database_search)
        if rag_config.get("knowledge_graph"):
            tools.append(graph_search)
        return tools
