"""Backward-compatibility re-export.

``CollectionsManager`` and ``Collection`` live in ``langconnect.services.collections``.
This module exists to avoid breaking any external code that still imports from here.
New code should import from ``langconnect.services.collections`` directly.
"""

from langconnect.services.collections import Collection, CollectionsManager

__all__ = ["Collection", "CollectionsManager"]
