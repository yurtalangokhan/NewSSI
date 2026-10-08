"""Safe bodies for ``PUT /users/{id}`` on Keycloak's declarative user profile."""

from typing import Any


def attribute_update(user: dict[str, Any], attributes: dict[str, Any]) -> dict[str, Any]:
    """Body that changes only ``attributes`` of a user read with ``GET /users/{id}``.

    Keycloak (24+) treats the PUT as a full profile replacement: email, first name
    and last name omitted from the body are cleared. Send the representation just
    read, with the new attributes, never an attributes-only body.
    """
    return {**user, "attributes": attributes}
