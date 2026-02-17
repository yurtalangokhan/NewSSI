import math
import re

import numexpr
from langchain_chroma import Chroma
from langchain_core.tools import BaseTool, tool, InjectedToolArg
from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import OllamaEmbeddings
from core import settings
from langchain_postgres import PGVector
from langchain_core.runnables import RunnableConfig
from typing import Annotated, List, Optional
import logging

logger = logging.getLogger(__name__)


# ============== User Context Tool ==============

@tool
def get_current_user_id(
    config: Annotated[RunnableConfig, InjectedToolArg]
) -> str:
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
        if settings.OPENAI_API_KEY:
            return OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)
        else:
            base_url = settings.OLLAMA_BASE_URL or "http://host.docker.internal:11434"
            return OllamaEmbeddings(base_url=base_url, model="nomic-embed-text")
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Embeddings: {e}") from e

def get_connection_string():
    """Get the PostgreSQL connection string."""
    return f"postgresql+psycopg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD.get_secret_value()}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"

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
    
    conn_str = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD.get_secret_value()}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    
    try:
        with psycopg.connect(conn_str) as conn:
            with conn.cursor() as cur:
                # Look up the name (table_id) from the uuid
                cur.execute(
                    "SELECT name FROM langchain_pg_collection WHERE uuid = %s",
                    (collection_uuid,)
                )
                row = cur.fetchone()
                if row:
                    logger.info(f"Resolved collection UUID {collection_uuid} to name {row[0]}")
                    return row[0]
                else:
                    # Maybe the collection_uuid is already the name
                    logger.warning(f"Collection UUID {collection_uuid} not found, using as-is")
                    return collection_uuid
    except Exception as e:
        logger.error(f"Error resolving collection UUID {collection_uuid}: {e}")
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

def database_search_func(
    query: str, 
    config: Annotated[RunnableConfig, InjectedToolArg]
) -> str:
    """Searches the company knowledge base for relevant information.
    
    Args:
        query (str): The search query to find information in the knowledge base.
    """
    try:
        # Get collection IDs from agent config
        configurable = config.get("configurable", {})
        rag_config = configurable.get("rag_config", {})
        collection_ids: List[str] = rag_config.get("collections", [])
        
        if not collection_ids:
            logger.warning("No collections configured for this agent. Check rag_config.collections in agent config.")
            return "Error: No knowledge base collections are configured for this agent."
        
        # Search across all configured collections
        all_documents = []
        for collection_uuid in collection_ids:
            try:
                # Convert UUID to PGVector collection name
                collection_name = get_collection_name_from_uuid(collection_uuid)
                logger.info(f"Searching collection: {collection_uuid} -> {collection_name}")
                vector_store = load_vector_store(collection_name)
                retriever = vector_store.as_retriever(search_kwargs={"k": 3})
                documents = retriever.invoke(query)
                all_documents.extend(documents)
                logger.info(f"Found {len(documents)} documents in collection {collection_name}")
            except Exception as e:
                logger.error(f"Error searching collection {collection_uuid}: {e}")
                continue
        
        if not all_documents:
            return "No relevant information found in the knowledge base."
        
        # Sort by relevance if needed and limit results
        return format_contexts(all_documents[:5])
        
    except Exception as e:
        logger.error(f"Error in database search: {e}")
        return f"Error searching database: {str(e)}"


database_search: BaseTool = tool(database_search_func)
database_search.name = "Database_Search"

