"""Shared response shaping helpers for tool modules.

Tool modules (e.g. ``mail_tools``) expose module-level functions that are not
methods on a ``BaseToolCategory`` subclass, yet still need the same
MCP-visible JSON contract. This module re-exports the canonical helpers from
:mod:`core.base` so every tool category shapes responses identically.
"""

from ..core.base import BaseToolCategory

success_response = BaseToolCategory.success_response
error_response = BaseToolCategory.error_response
