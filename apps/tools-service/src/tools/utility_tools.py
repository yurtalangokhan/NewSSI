"""
Utility Tools Category.
Provides general utility tools like UUID generation, encoding, hashing.
"""

import base64
import hashlib
import uuid
from typing import Any

from i18n import t

from ..core.base import BaseToolCategory


class UtilityTools(BaseToolCategory):
    """General utility tools."""

    @property
    def name(self) -> str:
        return "utilities"

    @property
    def description(self) -> str:
        return t(
            "categories.utilities.description",
            default="UUID generation, encoding, and hashing utilities",
        )

    @property
    def label(self) -> str:
        return t("categories.utilities.label", default="Utilities")

    def register_tools(self, mcp: Any) -> None:
        """Register all utility tools with MCP."""

        @mcp.tool()
        def generate_uuid() -> str:
            """
            Generate a random UUID.

            Returns:
                A new UUID v4 string
            """
            return str(uuid.uuid4())

        @mcp.tool()
        def encode_base64(text: str) -> str:
            """
            Encode text to Base64.

            Args:
                text: Text to encode

            Returns:
                Base64 encoded string
            """
            return base64.b64encode(text.encode()).decode()

        @mcp.tool()
        def decode_base64(encoded: str) -> str:
            """
            Decode Base64 to text.

            Args:
                encoded: Base64 encoded string

            Returns:
                Decoded text
            """
            try:
                return base64.b64decode(encoded).decode()
            except Exception as e:
                return t("utility.decode_error", error=str(e))

        @mcp.tool()
        def hash_text(text: str, algorithm: str = "sha256") -> str:
            """
            Generate hash of text.

            Args:
                text: Text to hash
                algorithm: Hash algorithm (md5, sha1, sha256, sha512)

            Returns:
                Hexadecimal hash string
            """
            algorithms = {
                "md5": hashlib.md5,
                "sha1": hashlib.sha1,
                "sha256": hashlib.sha256,
                "sha512": hashlib.sha512,
            }

            if algorithm not in algorithms:
                return t("utility.unknown_algorithm", algorithms=", ".join(algorithms.keys()))

            return algorithms[algorithm](text.encode()).hexdigest()
