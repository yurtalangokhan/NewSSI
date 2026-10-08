"""rag-service authenticates from the Authorization header, not from cookies.

`_extract_auth_token` fell back to fastapiusersauth / access_token / id_token /
session cookies when no Authorization header was present, so a browser merely
holding one of those cookies authenticated a cross-origin request without ever
presenting the token. agent-service dropped the same fallback (44c1d6f70) after
confirming production traffic always carries an explicit Authorization header;
this is the matching change.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from src.shared.auth import _extract_auth_token


def test_the_authorization_header_is_used():
    creds = SimpleNamespace(credentials="real-token")

    assert _extract_auth_token(creds) == "real-token"


def test_no_credentials_means_no_token():
    assert _extract_auth_token(None) is None


@pytest.mark.parametrize(
    "cookie", ["fastapiusersauth", "access_token", "id_token", "session"]
)
def test_the_extractor_cannot_see_cookies(cookie):
    """It takes only the parsed Authorization credentials, so no cookie can
    authenticate a request however it is named."""
    assert list(inspect.signature(_extract_auth_token).parameters) == ["credentials"]
    assert _extract_auth_token(None) is None
