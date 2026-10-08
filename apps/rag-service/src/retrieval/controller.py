"""Coordinate delegated retrieval and propagate typed service failures."""

from src.retrieval import service
from src.retrieval.contract import RetrievalResult, TrustedRetrievalContext
from src.retrieval.schemas import RetrievalRequestBody
from src.shared.delegation import resolve_user_id


async def retrieve_knowledge(
    body: RetrievalRequestBody,
    identity: str,
    delegated_user_id: str | None,
    tenant_id: str | None,
    access_token: str | None,
) -> RetrievalResult:
    context = TrustedRetrievalContext(
        user_id=resolve_user_id(identity, delegated_user_id),
        tenant_id=tenant_id if identity == "internal-service" else None,
    )
    return await service.retrieve_knowledge(body, context, access_token)
