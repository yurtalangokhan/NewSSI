"""allow_origins=["*"] combined with allow_credentials=True makes the
browser reflect any requesting Origin and send cookies with it. The code
path was already fixed to read ALLOWED_ORIGINS from the environment
instead of hardcoding "*", but the environment value itself can still
legitimately be "*". Spec T7.
"""

import pytest


def test_wildcard_origin_is_not_configured():
    from src.server import APP

    for middleware in APP.user_middleware:
        options = getattr(middleware, "kwargs", {}) or {}
        if "allow_origins" not in options:
            continue
        if options.get("allow_credentials"):
            assert "*" not in options["allow_origins"]


def test_settings_reject_wildcard_with_credentials():
    from security import validate_cors_policy

    with pytest.raises(ValueError, match="allow_credentials"):
        validate_cors_policy(origins=["*"], allow_credentials=True)
    validate_cors_policy(origins=["https://app.example"], allow_credentials=True)
    validate_cors_policy(origins=["*"], allow_credentials=False)
