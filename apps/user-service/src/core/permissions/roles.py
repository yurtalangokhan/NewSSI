"""Platform role naming shared by identity reads and writes."""

DEFAULT_ROLE_NAME = "enduser"


def display_role_name(role: str | None) -> str:
    """The primary role shown for a user; one without realm roles shows the default."""
    return role or DEFAULT_ROLE_NAME
