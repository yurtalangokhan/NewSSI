"""Resolve delegated identities without depending on HTTP framework types."""

from error_contract import (
    DelegatedIdentityRequiredError,
    TrustedIdentityRequiredError,
)


def resolve_user_id(identity: str, delegated_user_id: str | None) -> str:
    """Keep internal delegation separate from a public caller's identity."""
    if identity == "internal-service":
        delegated = (delegated_user_id or "").strip()
        if not delegated or delegated in {"internal-service", "dev-user"}:
            raise DelegatedIdentityRequiredError()
        return delegated
    if not identity:
        raise TrustedIdentityRequiredError()
    return identity
