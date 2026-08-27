"""Compatibility shim.

The ``AuthorizationClient`` now lives in ``integrations/authorization_client``.
This module re-exports the public symbols so existing ``from service.AuthorizationClient
import ...`` call sites keep working during the migration. Remove once all call
sites are updated to import from ``integrations.authorization_client``.
"""

from __future__ import annotations

from integrations.authorization_client import (
    AuthorizationClient,
    get_authorization_client,
)

__all__ = ["AuthorizationClient", "get_authorization_client"]
