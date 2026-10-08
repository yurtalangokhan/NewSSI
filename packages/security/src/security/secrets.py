"""Reading secrets that are stored as ``pydantic.SecretStr``/``SecretBytes``.

Both mask themselves under ``str()`` and ``repr()`` — that is the point, it
keeps credentials out of logs and tracebacks. The hazard is that the mask,
``'**********'`` (``"b'**********'"`` for ``SecretBytes``), is a perfectly
ordinary truthy string: code that forgets to unwrap does not crash, it quietly
authenticates with the wrong password, and the failure surfaces far from its
cause.

Route every settings-sourced secret through :func:`reveal_secret` (optional) or
:func:`require_secret` (mandatory) at the point of use.
"""

from typing import Any

from pydantic import SecretBytes, SecretStr

__all__ = ["require_secret", "reveal_secret"]


def reveal_secret(value: Any) -> str | None:
    """Return the plaintext of *value*, or ``None`` when it is unset or blank.

    Accepts ``SecretStr``, ``SecretBytes``, ``str`` or ``None`` so it can sit in
    front of settings fields whose type differs between services. Blank values
    collapse to ``None`` so that "configured but empty" and "not configured"
    behave alike.
    """
    if value is None:
        return None
    if isinstance(value, SecretStr):
        plaintext = value.get_secret_value()
    elif isinstance(value, SecretBytes):
        plaintext = value.get_secret_value().decode("utf-8")
    else:
        plaintext = str(value)
    plaintext = plaintext.strip()
    return plaintext or None


def require_secret(value: Any, name: str) -> str:
    """Return the plaintext of a required secret, raising when it is unset."""
    plaintext = reveal_secret(value)
    if plaintext is None:
        raise ValueError(f"Required secret {name} is not set in the environment")
    return plaintext
