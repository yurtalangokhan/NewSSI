"""Decrypting a mail configuration is scoped to whoever it is resolved for.

`get_decrypted_config` took a `_user_id` and ignored it, looking the row up by
id alone and returning the stored SMTP username and password. Listing mail
configurations is deliberately platform-wide (masked), but decryption is not —
any known config id handed back live credentials. The repository already
supported an owner filter; the service simply never passed one.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from error_contract import NotFoundError
import pytest

from service.auth.mail_config_service import MailConfigService


def _service(row):
    svc = MailConfigService.__new__(MailConfigService)
    svc.repo = SimpleNamespace(get_by_id=AsyncMock(return_value=row))
    return svc


@pytest.mark.asyncio
async def test_the_owner_filter_reaches_the_repository():
    svc = _service({"id": "cfg-1", "username": "u", "password_encrypted": None})

    await svc.get_decrypted_config("owner-1", "cfg-1")

    kwargs = svc.repo.get_by_id.await_args.kwargs
    args = svc.repo.get_by_id.await_args.args
    passed = kwargs.get("user_ids") or (args[1] if len(args) > 1 else None)
    assert passed, "the lookup was not scoped to an owner"
    assert "owner-1" in list(passed)


@pytest.mark.asyncio
async def test_a_config_owned_by_someone_else_is_not_decrypted():
    """The repository returns nothing once the owner filter excludes the row."""
    svc = _service(None)

    with pytest.raises(NotFoundError):
        await svc.get_decrypted_config("attacker-9", "cfg-1")
