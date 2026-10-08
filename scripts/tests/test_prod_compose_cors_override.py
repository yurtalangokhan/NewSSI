"""docker-compose-prod.yml must not force rag-service's CORS origins to '*'.

rag-service's own config.validate_cors_policy() refuses to start with
allow_origins=["*"] combined with allow_credentials=True (which this service
always sends) -- see packages/security/src/security/cors.py. An inline
`ALLOW_ORIGINS: '["*"]'` override in this compose file, placed after the
env_file that is supposed to be the single source of truth for production
settings, meant the service could never boot under this exact compose file
regardless of what .env.production said. See spec T7.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROD = ROOT / "deploy" / "docker" / "docker-compose-prod.yml"

_TOP_LEVEL_KEY = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*):\s*$")
_SERVICE_KEY = re.compile(r"^  ([A-Za-z0-9][A-Za-z0-9_.-]*):\s*$")


def _rag_service_block() -> list[str]:
    lines = PROD.read_text(encoding="utf-8").splitlines()
    in_services = False
    current: str | None = None
    block: list[str] = []
    for line in lines:
        if _TOP_LEVEL_KEY.match(line):
            in_services = line.strip() == "services:"
            current = None
            continue
        if not in_services:
            continue
        match = _SERVICE_KEY.match(line)
        if match:
            if current == "rag-service":
                break
            current = match.group(1)
            continue
        if current == "rag-service":
            block.append(line)
    return block


class ProdComposeCorsOverrideTests(unittest.TestCase):
    def test_rag_service_does_not_hardcode_allow_origins(self) -> None:
        block = _rag_service_block()
        self.assertTrue(block, "rag-service block not found in docker-compose-prod.yml")

        offending = [
            line
            for line in block
            if re.match(r"^\s*ALLOW_ORIGINS\s*:", line.split("#", 1)[0])
        ]
        self.assertEqual(
            offending,
            [],
            "ALLOW_ORIGINS is overridden inline in docker-compose-prod.yml's "
            "rag-service block; it must come from .env.production only: "
            f"{offending}",
        )


if __name__ == "__main__":
    unittest.main()
