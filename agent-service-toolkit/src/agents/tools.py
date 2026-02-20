import math
import re

import numexpr
from langchain_chroma import Chroma
from langchain_core.tools import BaseTool, tool, InjectedToolArg
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_ollama import OllamaEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from core import settings
from langchain_postgres import PGVector
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from typing import Annotated, List, Optional
import logging

logger = logging.getLogger(__name__)


# ============== LLM Entity Extraction (NER) ==============

class ExtractedEntities(BaseModel):
    """Entities extracted from user query for knowledge graph search."""

    names: List[str] = Field(
        default_factory=list,
        description=(
            "All named entities (persons, organizations, technologies, products, "
            "concepts, locations, etc.) that appear in the text. "
            "Return each entity as a short canonical name (e.g. 'Supabase', "
            "'PostgreSQL', 'OAuth 2.0').  Do NOT return generic words."
        ),
    )


_ENTITY_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an expert Named Entity Recognition (NER) system. "
            "Extract all meaningful named entities from the user's question. "
            "Focus on: technology names, product names, people, organizations, "
            "protocols, frameworks, services, and domain-specific concepts. "
            "Return canonical short names only. Do NOT include generic words "
            "like 'infrastructure', 'system', 'information', 'altyapı', etc.\n\n"
            "You MUST respond with ONLY a JSON object in this exact format:\n"
            '{{"names": ["Entity1", "Entity2"]}}\n\n'
            "Example:\n"
            'Input: "Supabase altyapısı hakkında bilgi ver"\n'
            'Output: {{"names": ["Supabase"]}}\n\n'
            'Input: "OAuth ve JWT kimlik doğrulama nasıl çalışır?"\n'
            'Output: {{"names": ["OAuth", "JWT"]}}\n\n'
            'Input: "PostgreSQL ile Neo4j arasındaki fark nedir?"\n'
            'Output: {{"names": ["PostgreSQL", "Neo4j"]}}\n\n'
            "Respond with ONLY the JSON, no explanation.",
        ),
        ("human", "{question}"),
    ]
)


def _parse_entity_response(text: str) -> List[str]:
    """Parse LLM response to extract entity names.

    Handles both structured JSON output and plain text responses.
    """
    import json

    text = text.strip()

    # Try parsing as JSON first
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "names" in data:
            return [n for n in data["names"] if isinstance(n, str) and len(n) >= 2]
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from within the text (LLM may add surrounding text)
    json_match = re.search(r'\{[^}]*"names"\s*:\s*\[([^\]]*)\][^}]*\}', text)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            if isinstance(data, dict) and "names" in data:
                return [n for n in data["names"] if isinstance(n, str) and len(n) >= 2]
        except json.JSONDecodeError:
            pass

    # Last resort: extract quoted strings
    quoted = re.findall(r'"([^"]{2,})"', text)
    if quoted:
        return quoted

    return []


def _get_entity_extraction_llm():
    """Get a lightweight LLM for entity extraction.

    Uses Ollama llama3.1:8b (local, fast, free) for NER entity extraction.
    Falls back to GPT-4o-mini if Ollama is not available.
    """
    ollama_base_url = settings.OLLAMA_BASE_URL or "http://host.docker.internal:11434"
    try:
        return ChatOllama(
            model="llama3.1:8b",
            temperature=0,
            base_url=ollama_base_url,
        )
    except Exception as e:
        logger.warning("Ollama ChatOllama init failed (%s), trying OpenAI fallback", e)
        if settings.OPENAI_API_KEY:
            return ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                api_key=settings.OPENAI_API_KEY.get_secret_value(),
            )
        raise RuntimeError("No LLM available for entity extraction") from e


def _extract_entities(question: str) -> List[str]:
    """Use LLM to extract named entities from a user question.

    This is the industry-standard approach (Tomaz Bratanic / LangChain+Neo4j):
    instead of doing naive string matching on the raw query, we first ask an
    LLM to identify the meaningful entities, then search those in the graph.

    Uses Ollama llama3.1:8b with robust JSON parsing (no structured output
    dependency) so it works reliably with local models.

    Example:
        "Supabase altyapısı hakkında bilgi ver" → ["Supabase"]
        "OAuth ve JWT kimlik doğrulama nasıl çalışır?" → ["OAuth", "JWT"]
    """
    try:
        llm = _get_entity_extraction_llm()
        chain = _ENTITY_EXTRACTION_PROMPT | llm
        result = chain.invoke({"question": question})
        # Extract text content from AIMessage
        text = result.content if hasattr(result, "content") else str(result)
        entities = _parse_entity_response(text)
        logger.info("NER extracted entities from '%s': %s", question, entities)
        print(f"[GRAPH_SEARCH] NER entities: {entities} (raw: {text[:200]})")
        return entities
    except Exception as e:
        logger.warning("LLM entity extraction failed, falling back to token split: %s", e)
        print(f"[GRAPH_SEARCH] NER failed ({e}), falling back to token split")
        # Fallback: simple token splitting (previous approach)
        return [t for t in question.split() if len(t) >= 3]


def _remove_lucene_special_chars(text: str) -> str:
    """Remove Lucene special characters from a search string."""
    special_chars = r'[+\-!(){}\[\]^"~*?:\\/]'
    return re.sub(special_chars, " ", text)


def _generate_fulltext_query(entity: str) -> str:
    """Generate a Neo4j full-text search query with fuzzy matching.

    Appends ~2 (2 character edit distance) to each word for typo tolerance.
    Words are combined with AND.

    Example:
        'Supabase' → 'Supabase~2'
        'Edge Functions' → 'Edge~2 AND Functions~2'
    """
    cleaned = _remove_lucene_special_chars(entity)
    words = [w for w in cleaned.split() if w]
    if not words:
        return ""
    parts = [f"{w}~2" for w in words]
    return " AND ".join(parts)


# ============== Neo4j Configuration ==============

NEO4J_URI = getattr(settings, "NEO4J_URI", None) or "bolt://neo4j:7687"
NEO4J_USERNAME = getattr(settings, "NEO4J_USERNAME", None) or "neo4j"
NEO4J_PASSWORD = getattr(settings, "NEO4J_PASSWORD", None) or "neo4j123"


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
                    print(f"[DB_SEARCH] Resolved collection UUID {collection_uuid} -> name='{row[0]}'")
                    return row[0]
                else:
                    print(f"[DB_SEARCH] WARNING: Collection UUID {collection_uuid} not found in DB, using as-is")
                    return collection_uuid
    except Exception as e:
        print(f"[DB_SEARCH] ERROR resolving collection UUID {collection_uuid}: {e}")
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
        
        print(f"[DB_SEARCH] Called with query='{query}', collection_ids={collection_ids}")
        
        if not collection_ids:
            print("[DB_SEARCH] WARNING: No collections configured!")
            return "Error: No knowledge base collections are configured for this agent."
        
        # Search across all configured collections
        all_documents = []
        for collection_uuid in collection_ids:
            try:
                # Convert UUID to PGVector collection name
                collection_name = get_collection_name_from_uuid(collection_uuid)
                print(f"[DB_SEARCH] Searching collection: {collection_uuid} -> '{collection_name}'")
                vector_store = load_vector_store(collection_name)
                retriever = vector_store.as_retriever(search_kwargs={"k": 5})
                documents = retriever.invoke(query)
                all_documents.extend(documents)
                print(f"[DB_SEARCH] Found {len(documents)} documents in collection '{collection_name}'")
                for i, doc in enumerate(documents):
                    title = doc.metadata.get("title", "no-title")
                    print(f"[DB_SEARCH]   doc[{i}]: title='{title}' | {doc.page_content[:200]}...")
            except Exception as e:
                print(f"[DB_SEARCH] ERROR searching collection {collection_uuid}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        if not all_documents:
            print("[DB_SEARCH] No documents found across all collections!")
            return "No relevant information found in the knowledge base."
        
        # Sort by relevance if needed and limit results
        result = format_contexts(all_documents[:5])
        print(f"[DB_SEARCH] Returning {len(all_documents[:5])} documents, total chars={len(result)}")
        return result
        
    except Exception as e:
        logger.error(f"Error in database search: {e}")
        return f"Error searching database: {str(e)}"


database_search: BaseTool = tool(database_search_func)
database_search.name = "Database_Search"


# ============== Graph Search Tool (Neo4j) ==============


def _get_neo4j_driver():
    """Get a Neo4j driver instance."""
    from neo4j import GraphDatabase

    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
    )


def _ensure_fulltext_index(driver) -> None:
    """Create a Neo4j full-text index on Entity.name if it doesn't exist.

    This is idempotent — safe to call on every search.
    """
    try:
        with driver.session() as session:
            session.run(
                "CREATE FULLTEXT INDEX entity_name_fulltext IF NOT EXISTS "
                "FOR (n:Entity) ON EACH [n.name]"
            )
    except Exception as e:
        # Index might already exist or Neo4j version doesn't support IF NOT EXISTS
        logger.debug("Full-text index creation note: %s", e)


def _graph_entity_search(query: str, collection_id: str, limit: int = 10) -> list[dict]:
    """Search Neo4j for entities matching the query using LLM NER + full-text fuzzy search.

    Industry-standard approach (LangChain + Neo4j / Tomaz Bratanic):
    1. LLM extracts named entities from the user's question
    2. Each entity is searched via Neo4j full-text index with fuzzy matching (~2)
    3. Results are filtered by collection_id and deduplicated

    Falls back to token-based CONTAINS search if full-text index is unavailable.
    """
    # Step 1: LLM-based entity extraction
    extracted_entities = _extract_entities(query)
    if not extracted_entities:
        logger.info("No entities extracted from query: '%s'", query)
        return []

    driver = _get_neo4j_driver()
    try:
        _ensure_fulltext_index(driver)

        all_results: list[dict] = []
        seen_names: set[str] = set()

        with driver.session() as session:
            for entity in extracted_entities:
                ft_query = _generate_fulltext_query(entity)
                if not ft_query:
                    continue

                try:
                    # Step 2: Full-text fuzzy search with collection filter
                    result = session.run(
                        """
                        CALL db.index.fulltext.queryNodes(
                            'entity_name_fulltext', $ft_query, {limit: $search_limit}
                        ) YIELD node, score
                        WHERE node.collection_id = $cid
                        RETURN node.name AS name, node.label AS label, score
                        ORDER BY score DESC
                        LIMIT $limit
                        """,
                        ft_query=ft_query,
                        cid=collection_id,
                        search_limit=limit * 3,  # fetch more, then filter
                        limit=limit,
                    )
                    for record in result:
                        name = record["name"]
                        if name not in seen_names:
                            seen_names.add(name)
                            all_results.append({
                                "name": name,
                                "label": record.get("label", "Entity"),
                                "score": record.get("score", 0),
                                "matched_entity": entity,
                            })
                    print(f"[GRAPH_SEARCH] Fulltext '{ft_query}' → {len([r for r in all_results if r.get('matched_entity') == entity])} hits")

                except Exception as ft_err:
                    # Full-text index might not be available — fallback to CONTAINS
                    logger.warning("Full-text search failed for '%s', using CONTAINS fallback: %s", entity, ft_err)
                    print(f"[GRAPH_SEARCH] Fulltext failed, CONTAINS fallback for '{entity}'")
                    result = session.run(
                        """
                        MATCH (n:Entity {collection_id: $cid})
                        WHERE toLower(n.name) CONTAINS toLower($q)
                        RETURN n.name AS name, n.label AS label
                        LIMIT $limit
                        """,
                        cid=collection_id,
                        q=entity,
                        limit=limit,
                    )
                    for record in result:
                        name = record["name"]
                        if name not in seen_names:
                            seen_names.add(name)
                            all_results.append({
                                "name": name,
                                "label": record.get("label", "Entity"),
                                "matched_entity": entity,
                            })

        # Sort by score (fulltext relevance) descending
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        print(f"[GRAPH_SEARCH] Total entities found: {len(all_results)} for query: '{query}'")
        return all_results[:limit]
    finally:
        driver.close()


def _graph_context_search(entity_names: list[str], collection_id: str, depth: int = 2) -> str:
    """Get context (triples) around given entities from Neo4j."""
    driver = _get_neo4j_driver()
    lines: list[str] = []
    try:
        with driver.session() as session:
            for name in entity_names:
                result = session.run(
                    f"""
                    MATCH (n:Entity {{collection_id: $cid, name: $name}})
                    OPTIONAL MATCH path = (n)-[*1..{depth}]-(m:Entity {{collection_id: $cid}})
                    UNWIND relationships(path) AS r
                    WITH DISTINCT startNode(r) AS s, type(r) AS rtype, endNode(r) AS t
                    RETURN s.name AS src, rtype, t.name AS tgt
                    LIMIT 50
                    """,
                    cid=collection_id,
                    name=name,
                )
                for record in result:
                    lines.append(f"{record['src']} --[{record['rtype']}]--> {record['tgt']}")
    finally:
        driver.close()

    return "\n".join(lines) if lines else ""


def _reciprocal_rank_fusion(
    vector_results: list[str],
    graph_results: list[str],
    k: int = 60,
    vector_weight: float = 0.5,
    graph_weight: float = 0.5,
) -> list[tuple[str, float]]:
    """Combine results from two sources using RRF scoring."""
    scores: dict[str, float] = {}
    for rank, item in enumerate(vector_results):
        scores[item] = scores.get(item, 0) + vector_weight / (k + rank + 1)
    for rank, item in enumerate(graph_results):
        scores[item] = scores.get(item, 0) + graph_weight / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def graph_search_func(
    query: str,
    config: Annotated[RunnableConfig, InjectedToolArg],
) -> str:
    """Searches the knowledge graph for entities and their relationships.

    Uses hybrid retrieval: combines vector similarity search with graph
    traversal using Reciprocal Rank Fusion (RRF) scoring.

    Args:
        query (str): The search query to find information in the knowledge graph.
    """
    try:
        configurable = config.get("configurable", {})
        rag_config = configurable.get("rag_config", {})
        collection_ids: List[str] = rag_config.get("collections", [])

        if not collection_ids:
            logger.warning("No collections configured for graph search.")
            return "Error: No knowledge base collections are configured for this agent."

        all_context_parts: list[str] = []

        for collection_uuid in collection_ids:
            try:
                # --- 1. Vector Search (Cosine Similarity) ---
                collection_name = get_collection_name_from_uuid(collection_uuid)
                vector_store = load_vector_store(collection_name)
                retriever = vector_store.as_retriever(search_kwargs={"k": 5})
                vector_docs = retriever.invoke(query)
                vector_texts = [doc.page_content for doc in vector_docs]

                # --- 2. Graph Search (LLM NER + Full-text Fuzzy + Context) ---
                entities = _graph_entity_search(query, collection_uuid, limit=10)
                entity_names = [e["name"] for e in entities]
                graph_context = _graph_context_search(entity_names, collection_uuid)
                graph_items = entity_names  # for RRF ranking
                print(f"[GRAPH_SEARCH] Entities for RRF: {entity_names}")

                # --- 3. RRF Fusion ---
                rrf_ranked = _reciprocal_rank_fusion(
                    vector_texts, graph_items,
                    vector_weight=0.5, graph_weight=0.5,
                )

                # --- 4. Build combined context ---
                if vector_texts:
                    all_context_parts.append("=== Vector Search Results ===")
                    all_context_parts.extend(vector_texts[:3])

                if graph_context:
                    all_context_parts.append("\n=== Knowledge Graph Context ===")
                    all_context_parts.append(graph_context)

                if entities:
                    all_context_parts.append("\n=== Discovered Entities ===")
                    for e in entities[:10]:
                        matched = e.get('matched_entity', '')
                        label = e.get('label', 'Entity')
                        score = e.get('score', 0)
                        if matched:
                            all_context_parts.append(f"- {e['name']} ({label}) [matched: '{matched}', score: {score:.3f}]")
                        else:
                            all_context_parts.append(f"- {e['name']} ({label})")

            except Exception as e:
                logger.error(f"Error in graph search for collection {collection_uuid}: {e}")
                continue

        if not all_context_parts:
            return "No relevant information found in the knowledge graph."

        return "\n\n".join(all_context_parts)

    except Exception as e:
        logger.error(f"Error in graph search: {e}")
        return f"Error searching knowledge graph: {str(e)}"


graph_search: BaseTool = tool(graph_search_func)
graph_search.name = "Graph_Search"

