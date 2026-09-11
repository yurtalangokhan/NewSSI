"""Tests for resolve_user_service_id — the shared helper extracted from
require_permission's inline logic so the flow audit emitter (P3 Task 19)
doesn't duplicate it a third time.

Brief: .tmp/flow-canvas-task-19-brief.md
"""

from __future__ import annotations

from service.AuthService import AuthenticatedUser, resolve_user_service_id


def _user(claims: dict | None = None, user_id: str = "some-id") -> AuthenticatedUser:
    return AuthenticatedUser(user_id=user_id, email="u@local.dev", claims=claims or {})


def test_resolves_real_user_service_id_from_claims():
    user = _user(claims={"user_service_user": {"id": "real-uuid-123"}})

    assert resolve_user_service_id(user) == "real-uuid-123"


def test_returns_none_when_claim_absent():
    user = _user(claims={})

    assert resolve_user_service_id(user) is None


def test_returns_none_when_claim_present_but_id_missing():
    user = _user(claims={"user_service_user": {"name": "no id here"}})

    assert resolve_user_service_id(user) is None


def test_returns_none_when_claim_is_not_a_dict():
    user = _user(claims={"user_service_user": "unexpected-shape"})

    assert resolve_user_service_id(user) is None
