"""Knowledge system prompt builder.

Generates retrieval-specific system prompt addenda based on which
knowledge types are active for an agent.  Adding a new retrieval type
requires only adding a new KnowledgeMode value and its addendum string.
"""

from datetime import datetime
from enum import Enum


class KnowledgeMode(Enum):
    DOCUMENT_ONLY = "document_only"
    GRAPH_ONLY = "graph_only"
    HYBRID = "hybrid"


_CURRENT_DATE = datetime.now().strftime("%B %d, %Y")

_DOCUMENT_ADDENDUM = f"""
---Knowledge Base Access---
Today's date is {_CURRENT_DATE}.
You have access to **Database_Search**, which performs vector similarity search over
ingested document collections.

Search rules:
  • ALWAYS call Database_Search before answering any factual question.
  • Issue multiple searches for complex questions — decompose into focused sub-queries.
  • Cite every factual claim: "... [Data: Sources (12, 34)]."
  • Do not list more than 5 source IDs; use "+more" for additional.
  • Include markdown-formatted links to any citations where available.
    ONLY USE LINKS RETURNED BY THE TOOL.
  • If the retrieved data is insufficient, say so clearly. Do NOT fabricate information.
  • Only use information from the knowledge base. Do not use outside sources.

NOTE: THE USER CANNOT SEE THE RAW TOOL RESPONSE — synthesise the results into natural language.
"""

_GRAPH_ADDENDUM = f"""
---Knowledge Graph Access---
Today's date is {_CURRENT_DATE}.
You have access to **Graph_Search**, which performs hybrid retrieval combining:
  1. Vector similarity search (cosine on document embeddings)
  2. BM25 graph search (Neo4j fulltext on entity names / labels)
  3. Entity-centric Reciprocal Rank Fusion (RRF) to merge results

Each call returns Vector Search Results, RRF-Ranked Entities, and
Knowledge Graph Context — use ALL of these sections when building your answer.

Multi-Step Search Strategy:
ALWAYS search before answering any factual question.  You may — and SHOULD —
call Graph_Search **multiple times** when a question is complex:

  1. Decompose – Break a complex question into 2-5 focused sub-queries,
     each targeting a single entity, concept, or relationship.
  2. Explore  – If the first search surfaces new entities, follow them up.
  3. Verify   – If two sources conflict, search for additional evidence.
  4. Synthesise – Merge results into a coherent answer.  Trace the reasoning
     chain from directly mentioned entities through their relationships.

Do NOT ask compound sub-queries.  Each search should focus on one entity or
relationship at a time — this maximises retrieval precision.

Citation Rules:
  • Every factual claim MUST cite its source: "... [Data: Sources (12, 34)]."
  • Do not list more than 5 source IDs; use "+more" for additional.
  • Do not include information where supporting evidence is not provided.
  • ONLY USE LINKS RETURNED BY THE TOOLS.

Formatting:
  • Translate ALL graph relationships into fluent natural language.
    NEVER show raw notation like "A --[RELATES_TO]--> B".
  • Explain WHY components are related, not just THAT they are related.

NOTE: THE USER CANNOT SEE THE RAW TOOL RESPONSE — synthesise the results.
"""

_HYBRID_ADDENDUM = f"""
---Knowledge Base Access---
Today's date is {_CURRENT_DATE}.
You have two retrieval tools available:

  • **Database_Search** – Vector similarity search over document collections.
    Use for broad document retrieval and keyword-based questions.

  • **Graph_Search** – Hybrid vector + Neo4j knowledge graph search.
    Use for entity relationships, concept graphs, and multi-hop reasoning.

Search strategy:
  1. Decompose complex questions into focused sub-queries.
  2. Use Database_Search for document-level retrieval.
  3. Use Graph_Search for entity relationships discovered in step 2.
  4. Synthesise results from BOTH sources into a single coherent answer.
  5. When sources conflict, note the discrepancy and search for additional evidence.

Citation Rules:
  • Cite every factual claim: "... [Data: Sources (12, 34)]."
  • Do not list more than 5 source IDs per reference; use "+more" for additional.
  • ONLY USE LINKS RETURNED BY THE TOOLS.
  • Do NOT fabricate information.

NOTE: THE USER CANNOT SEE THE RAW TOOL RESPONSE — synthesise the results into natural language.
"""

_ADDENDUM_MAP: dict[KnowledgeMode, str] = {
    KnowledgeMode.DOCUMENT_ONLY: _DOCUMENT_ADDENDUM,
    KnowledgeMode.GRAPH_ONLY: _GRAPH_ADDENDUM,
    KnowledgeMode.HYBRID: _HYBRID_ADDENDUM,
}


class KnowledgeSystemPromptBuilder:
    """Builds system prompt addenda for RAG-enabled agents.

    Open for extension: adding a new retrieval type requires only adding a
    new KnowledgeMode value and its addendum string to _ADDENDUM_MAP.
    """

    @classmethod
    def determine_mode(cls, rag_config: dict) -> KnowledgeMode | None:
        """Return the KnowledgeMode implied by rag_config, or None if no collections."""
        has_doc = bool(rag_config.get("document_processing"))
        has_graph = bool(rag_config.get("knowledge_graph"))
        if has_doc and has_graph:
            return KnowledgeMode.HYBRID
        if has_doc:
            return KnowledgeMode.DOCUMENT_ONLY
        if has_graph:
            return KnowledgeMode.GRAPH_ONLY
        return None

    @classmethod
    def build_full_prompt(cls, base_prompt: str | None, mode: KnowledgeMode) -> str:
        """Concatenate the user's base instructions with the RAG addendum."""
        addendum = _ADDENDUM_MAP[mode]
        parts = [p for p in (base_prompt, addendum) if p]
        return "\n".join(parts).strip()
