"""Compatibility shim.

The Airbyte API client now lives in ``integrations/airbyte_api_client``. This
module re-exports the public symbols so existing
``from service.AirbyteApiClientService import ...`` call sites keep working
during the migration. Remove once all call sites are updated to import from
``integrations.airbyte_api_client``.
"""

from __future__ import annotations

from integrations.airbyte_api_client import (
    AirbyteAPIClient,
    AirbyteAPIError,
    get_airbyte_client,
)

__all__ = ["AirbyteAPIClient", "AirbyteAPIError", "get_airbyte_client"]
