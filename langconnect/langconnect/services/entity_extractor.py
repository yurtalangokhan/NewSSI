"""Entity & relation extraction from text using LLMGraphTransformer.

Uses LangChain's experimental LLMGraphTransformer to convert unstructured text
into structured graph triples (subject, predicate, object).
"""

import logging
from typing import Any

from langchain_core.documents import Document

from langconnect.config import EMBEDDING_PROVIDER, OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL
from langconnect.models.graph import (
    ExtractedEntity,
    ExtractedRelation,
    ExtractionResult,
)

logger = logging.getLogger(__name__)


def _get_llm():
    """Get a chat model for entity extraction.

    Uses the same provider logic as embeddings but returns a chat model
    suitable for structured extraction.
    """
    provider = EMBEDDING_PROVIDER.lower()
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        # Use a capable model for extraction; fall back to llama3.1
        model_name = OLLAMA_EMBED_MODEL
        # For extraction we need a chat model, not embedding model
        # Default to llama3.1:8b which is good at structured extraction
        return ChatOllama(
            model="llama3.1:8b",
            base_url=OLLAMA_BASE_URL,
            temperature=0,
        )
    else:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model="gpt-4o-mini", temperature=0)


class EntityExtractor:
    """Extract entities and relations from document chunks using LLMGraphTransformer."""

    def __init__(
        self,
        allowed_nodes: list[str] | None = None,
        allowed_relationships: list[str] | None = None,
    ) -> None:
        self.allowed_nodes = allowed_nodes
        self.allowed_relationships = allowed_relationships
        self._transformer = None

    def _get_transformer(self):
        """Lazy-load the LLMGraphTransformer."""
        if self._transformer is None:
            from langchain_experimental.graph_transformers import (
                LLMGraphTransformer,
            )

            llm = _get_llm()
            kwargs: dict[str, Any] = {"llm": llm}
            if self.allowed_nodes:
                kwargs["allowed_nodes"] = self.allowed_nodes
            if self.allowed_relationships:
                kwargs["allowed_relationships"] = self.allowed_relationships

            self._transformer = LLMGraphTransformer(**kwargs)
        return self._transformer

    async def extract_from_text(
        self,
        text: str,
        chunk_id: str | None = None,
    ) -> ExtractionResult:
        """Extract entities and relations from a single text chunk.

        Args:
            text: The text to extract from.
            chunk_id: Optional identifier for the source chunk.

        Returns:
            ExtractionResult with extracted entities and relations.
        """
        if not text.strip():
            return ExtractionResult(chunk_id=chunk_id)

        transformer = self._get_transformer()
        doc = Document(page_content=text)

        try:
            graph_documents = await transformer.aconvert_to_graph_documents([doc])
        except Exception:
            logger.exception("Entity extraction failed for chunk %s", chunk_id)
            return ExtractionResult(chunk_id=chunk_id)

        entities: list[ExtractedEntity] = []
        relations: list[ExtractedRelation] = []
        seen_entities: set[str] = set()

        for graph_doc in graph_documents:
            for node in graph_doc.nodes:
                key = f"{node.id}:{node.type}"
                if key not in seen_entities:
                    seen_entities.add(key)
                    entities.append(
                        ExtractedEntity(
                            name=str(node.id),
                            label=node.type,
                            properties=node.properties if hasattr(node, "properties") else {},
                        )
                    )
            for rel in graph_doc.relationships:
                relations.append(
                    ExtractedRelation(
                        source=str(rel.source.id),
                        target=str(rel.target.id),
                        type=rel.type,
                        properties=rel.properties if hasattr(rel, "properties") else {},
                    )
                )

        logger.info(
            "Extracted %d entities and %d relations from chunk %s",
            len(entities),
            len(relations),
            chunk_id,
        )
        return ExtractionResult(
            chunk_id=chunk_id,
            entities=entities,
            relations=relations,
        )

    async def extract_from_documents(
        self,
        documents: list[Document],
    ) -> list[ExtractionResult]:
        """Extract entities and relations from multiple documents.

        Args:
            documents: List of LangChain Document objects.

        Returns:
            List of ExtractionResult, one per document.
        """
        results: list[ExtractionResult] = []
        for doc in documents:
            chunk_id = doc.metadata.get("file_id") or doc.id or None
            result = await self.extract_from_text(
                text=doc.page_content,
                chunk_id=str(chunk_id) if chunk_id else None,
            )
            results.append(result)
        return results
