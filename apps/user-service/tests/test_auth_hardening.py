"""Session cookies must be `Secure` outside development, and the shared
internal-service token must be compared in constant time.

`secure=False` was hardcoded on every auth cookie, so a single plaintext hop
(a misconfigured ingress, a stray http:// link) leaks a live session. And the
internal token was compared with `==`, which returns as soon as it finds a
differing byte — a remotely measurable difference an attacker can walk one
byte at a time.
"""

from __future__ import annotations

import inspect

import pytest

from src.api import dependencies
from src.controller.auth_controller import AuthController


class _Recorder:
    def __init__(self):
        self.cookies: list[dict] = []

    def set_cookie(self, **kwargs):
        self.cookies.append(kwargs)


@pytest.fixture
def controller():
    return AuthController.__new__(AuthController)


def _set(controller, response, monkeypatch, *, secure: bool):
    monkeypatch.setattr("src.controller.auth_controller.cookies_should_be_secure", lambda: secure)
    controller._set_cookies(
        response,
        access_token="a",
        refresh_token="r",
        id_token=None,
        expires_in=300,
        refresh_expires_in=3600,
    )


def test_cookies_are_secure_when_the_deployment_says_so(controller, monkeypatch):
    response = _Recorder()
    monkeypatch.setattr(AuthController, "_can_set_id_token_cookie", lambda *a, **k: False)

    _set(controller, response, monkeypatch, secure=True)

    assert response.cookies, "no cookies were set"
    assert all(cookie["secure"] is True for cookie in response.cookies)


def test_cookies_may_stay_insecure_for_local_http_development(controller, monkeypatch):
    response = _Recorder()
    monkeypatch.setattr(AuthController, "_can_set_id_token_cookie", lambda *a, **k: False)

    _set(controller, response, monkeypatch, secure=False)

    assert all(cookie["secure"] is False for cookie in response.cookies)


def test_internal_token_is_compared_in_constant_time():
    """Read the source rather than timing it: a timing assertion would be
    flaky, while `==` on a secret is unambiguous to spot."""
    source = inspect.getsource(dependencies)

    assert "hmac.compare_digest" in source
    for line in source.splitlines():
        stripped = line.strip()
        if "INTERNAL_SERVICE_TOKEN" in stripped and "==" in stripped:
            pytest.fail(f"secret compared with == : {stripped}")
