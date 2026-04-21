import math
import os
import re
from typing import Annotated

import numexpr
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, InjectedToolArg, tool
from langchain_ollama import OllamaEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

from core.env import env
from core.logger import get_logger

logger = get_logger(__name__)


# ============== User Context Tool ==============


@tool
def get_current_user_id(config: Annotated[RunnableConfig, InjectedToolArg]) -> str:
    """
    Get the current user's ID from the session context.
    Use this tool to get the authenticated user's ID before creating projects or tasks.

    Returns:
        str: The current user's UUID
    """
    user_id = config.get("configurable", {}).get("user_id")
    if not user_id:
        return "Error: No user_id found in session context. Please ensure you are authenticated."
    return user_id


def calculator_func(expression: str) -> str:
    """Calculates a math expression using numexpr.

    Useful for when you need to answer questions about math using numexpr.
    This tool is only for math questions and nothing else. Only input
    math expressions.

    Args:
        expression (str): A valid numexpr formatted math expression.

    Returns:
        str: The result of the math expression.
    """

    try:
        local_dict = {"pi": math.pi, "e": math.e}
        output = str(
            numexpr.evaluate(
                expression.strip(),
                global_dict={},  # restrict access to globals
                local_dict=local_dict,  # add common mathematical functions
            )
        )
        return re.sub(r"^\[|\]$", "", output)
    except Exception as e:
        raise ValueError(
            f'calculator("{expression}") raised error: {e}.'
            " Please try again with a valid numerical expression"
        )


calculator: BaseTool = tool(calculator_func)
calculator.name = "Calculator"


# Format retrieved documents
def format_contexts(docs):
    return "\n\n".join(doc.page_content for doc in docs)


def get_embeddings():
    """Get the configured embeddings model."""
    try:
        openai_key = env.get("OPENAI_API_KEY")
        if openai_key:
            return OpenAIEmbeddings(api_key=openai_key)
        else:
            base_url = env.OLLAMA_BASE_URL or "http://host.docker.internal:11434"
            return OllamaEmbeddings(base_url=base_url, model="nomic-embed-text")
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Embeddings: {e}") from e


def get_connection_string():
    """Get the PostgreSQL connection string."""
    return f"postgresql+psycopg://{env.POSTGRES_USER}:{env.POSTGRES_PASSWORD}@{env.POSTGRES_HOST}:{env.POSTGRES_PORT}/{env.POSTGRES_DB}"


def get_collection_name_from_uuid(collection_uuid: str) -> str:
    """
    Convert a LangConnect collection UUID to PGVector collection name (table_id).

    LangConnect stores:
    - uuid column: the ID used in agent config (e.g., 124b3af0-86aa-4978-9e29-0eb5c8b28be4)
    - name column: the PGVector collection name/table_id (e.g., db4ca372-487b-4f27-9be4-94ebed523295)

    Args:
        collection_uuid: The UUID from agent config (rag_config.collections)

    Returns:
        The PGVector collection name, or the original UUID if not found.
    """
    import psycopg

    conn_str = f"postgresql://{env.POSTGRES_USER}:{env.POSTGRES_PASSWORD}@{env.POSTGRES_HOST}:{env.POSTGRES_PORT}/{env.POSTGRES_DB}"

    try:
        with psycopg.connect(conn_str) as conn:
            with conn.cursor() as cur:
                # Look up the name (table_id) from the uuid
                cur.execute(
                    "SELECT name FROM langchain_pg_collection WHERE uuid = %s", (collection_uuid,)
                )
                row = cur.fetchone()
                if row:
                    logger.debug(
                        "Resolved collection UUID %s -> name='%s'", collection_uuid, row[0]
                    )
                    return row[0]
                else:
                    logger.warning(
                        "Collection UUID %s not found in DB, using as-is", collection_uuid
                    )
                    return collection_uuid
    except Exception as e:
        logger.error("Error resolving collection UUID %s: %s", collection_uuid, e)
        return collection_uuid


def load_vector_store(collection_name: str):
    """Load a PGVector store for a specific collection."""
    embeddings = get_embeddings()
    connection = get_connection_string()

    return PGVector(
        embeddings=embeddings,
        collection_name=collection_name,
        connection=connection,
        use_jsonb=True,
    )


def database_search_func(query: str, config: Annotated[RunnableConfig, InjectedToolArg]) -> str:
    """Searches the company knowledge base for relevant information.

    Args:
        query (str): The search query to find information in the knowledge base.
    """
    try:
        # Get collection IDs from agent config
        configurable = config.get("configurable", {})
        rag_config = configurable.get("rag_config", {})
        # Prefer rag_config.document_processing; fall back to legacy rag_config.collections
        collection_ids: list[str] = (
            rag_config.get("document_processing") or rag_config.get("collections", [])
        )

        logger.debug(
            "Database search called with query='%s', collection_ids=%s", query, collection_ids
        )

        if not collection_ids:
            logger.warning("No collections configured!")
            return "Error: No knowledge base collections are configured for this agent."

        # Search across all configured collections
        all_documents = []
        for collection_uuid in collection_ids:
            try:
                collection_name = get_collection_name_from_uuid(collection_uuid)
                logger.debug("Searching collection: %s -> '%s'", collection_uuid, collection_name)
                vector_store = load_vector_store(collection_name)
                retriever = vector_store.as_retriever(search_kwargs={"k": 5})
                documents = retriever.invoke(query)
                all_documents.extend(documents)
                logger.debug(
                    "Found %d documents in collection '%s'", len(documents), collection_name
                )
                for i, doc in enumerate(documents):
                    title = doc.metadata.get("title", "no-title")
                    logger.debug("  doc[%d]: title='%s' | %s...", i, title, doc.page_content[:200])
            except Exception as e:
                logger.error("Error searching collection %s: %s", collection_uuid, e)
                continue

        if not all_documents:
            logger.warning("No documents found across all collections!")
            return "No relevant information found in the knowledge base."

        result = format_contexts(all_documents[:5])
        logger.debug("Returning %d documents, total chars=%d", len(all_documents[:5]), len(result))
        return result

    except Exception as e:
        logger.error(f"Error in database search: {e}")
        return f"Error searching database: {str(e)}"


database_search: BaseTool = tool(database_search_func)
database_search.name = "Database_Search"


# ============== Graph Search Tool (Neo4j via LangConnect API) ==============

# LangConnect API base URL (service-to-service within Docker network)
_LANGCONNECT_BASE_URL = os.environ.get("LANGCONNECT_API_URL", "http://langconnect-api:8080")
_LANGCONNECT_SERVICE_TOKEN = os.environ.get(
    "LANGCONNECT_SERVICE_TOKEN", "internal-service-key-2026"
)


def graph_search_func(
    query: str,
    config: Annotated[RunnableConfig, InjectedToolArg],
) -> str:
    """Searches the knowledge graph for entities and their relationships.

    Uses LangConnect's hybrid search API which combines vector similarity
    search with BM25 graph search using entity-centric RRF scoring.

    Args:
        query (str): The search query to find information in the knowledge graph.
    """
    import httpx

    try:
        configurable = config.get("configurable", {})
        rag_config = configurable.get("rag_config", {})
        # Prefer rag_config.knowledge_graph; fall back to legacy rag_config.collections
        collection_ids: list[str] = (
            rag_config.get("knowledge_graph") or rag_config.get("collections", [])
        )

        if not collection_ids:
            logger.warning("No collections configured for graph search.")
            return "Error: No knowledge base collections are configured for this agent."

        all_context_parts: list[str] = []

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "python-httpx",
            "X-Internal-Service-Token": _LANGCONNECT_SERVICE_TOKEN,
        }

        for collection_uuid in collection_ids:
            try:
                payload = {
                    "query": query,
                    "collection_id": collection_uuid,
                    "limit": 10,
                    "vector_weight": 0.4,
                    "graph_weight": 0.6,
                }

                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(
                        f"{_LANGCONNECT_BASE_URL}/graph/search",
                        json=payload,
                        headers=headers,
                    )
                    resp.raise_for_status()
                    result = resp.json()

                context = result.get("context", "")
                nodes = result.get("nodes", [])
                edges = result.get("edges", [])
                score = result.get("score", 0)

                logger.info(
                    "[GRAPH_SEARCH] collection=%s nodes=%d edges=%d score=%.4f",
                    collection_uuid,
                    len(nodes),
                    len(edges),
                    score,
                )

                if context:
                    all_context_parts.append(context)

            except httpx.HTTPStatusError as exc:
                logger.error(
                    "Graph search HTTP error for collection %s: %s %s",
                    collection_uuid,
                    exc.response.status_code,
                    exc.response.text[:200],
                )
                continue
            except Exception as e:
                logger.error("Graph search failed for collection %s: %s", collection_uuid, e)
                continue

        if not all_context_parts:
            return "No relevant information found in the knowledge graph."

        return "\n\n".join(all_context_parts)

    except Exception as e:
        logger.error("Error in graph search: %s", e)
        return f"Error searching knowledge graph: {str(e)}"


graph_search: BaseTool = tool(graph_search_func)
graph_search.name = "Graph_Search"
