"""Composition point for the retrieval gateway the flow nodes run against."""

from agents.graphs.flow.nodes.retrieval_ports import RetrievalGateway
from integrations.rag_retrieval_gateway import RagRetrievalGateway


def default_retrieval_gateway() -> RetrievalGateway:
    """The rag-service-backed gateway flow retrieval nodes use in production."""
    return RagRetrievalGateway()
