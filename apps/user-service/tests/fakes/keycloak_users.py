"""Keycloak 26 user-update semantics, as observed against the running realm.

``PUT /users/{id}`` replaces the user profile rather than merging it: email,
first name and last name missing from the body are cleared, and ``attributes``
is replaced wholesale. The username survives because Keycloak keeps it when
omitted. A merge-based fake hid a data-loss bug, so fakes use this instead.
"""

import copy

CLEARED_WHEN_OMITTED = ("email", "firstName", "lastName")


def put_user(stored: dict, body: dict) -> None:
    for field in CLEARED_WHEN_OMITTED:
        stored[field] = body.get(field)
    stored["attributes"] = copy.deepcopy(body.get("attributes") or {})
    for field, value in body.items():
        if field not in (*CLEARED_WHEN_OMITTED, "attributes", "id"):
            stored[field] = copy.deepcopy(value)
