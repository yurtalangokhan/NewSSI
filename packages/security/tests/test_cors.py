"""The origin/credential safety rule.

The origin *parsing* tests live in the config_manager package, because that is
where the function now lives.
"""

import pytest

from security import validate_cors_policy


def test_wildcard_with_credentials_is_rejected():
    with pytest.raises(ValueError, match="cannot be combined"):
        validate_cors_policy(origins=["*"], allow_credentials=True)


def test_wildcard_without_credentials_is_allowed():
    validate_cors_policy(origins=["*"], allow_credentials=False)


def test_explicit_origins_with_credentials_are_allowed():
    validate_cors_policy(origins=["https://a.test"], allow_credentials=True)
