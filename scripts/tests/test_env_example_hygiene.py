"""The shipped env example must not carry a real deployment's details.

`configs/.env` is the single environment file every deployment reads, and it
still pinned one specific internal host by IP in seven places — so a fresh
checkout silently pointed at somebody's private network, and anyone reading
the repo learned an internal address. The generator was already fixed to use
DEPLOY_HOST/localhost; the example it documents was not.

`OVERRIDE_API_PRODUCTION` is the other half: the generic /api/* proxy is
refused outside development *unless* that flag is true, and the generator
emitted it as true. A generated .env carried to a production build therefore
opened the proxy with nothing else changed.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / "configs" / ".env"
ENV_MANAGER = REPO_ROOT / "packages" / "config-manager" / "src" / "config_manager" / "manager.py"

# Any RFC1918 / carrier-grade literal. A loopback address is fine in an example.
PRIVATE_IP = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
)


def test_the_env_example_pins_no_private_host_address():
    offenders = sorted(
        f"{number}: {line.strip()}"
        for number, line in enumerate(ENV_EXAMPLE.read_text(encoding="utf-8").splitlines(), 1)
        if PRIVATE_IP.search(line)
    )

    assert offenders == [], f"configs/.env names a private host:\n" + "\n".join(offenders)


def test_the_generator_does_not_default_the_production_api_proxy_on():
    source = ENV_MANAGER.read_text(encoding="utf-8")
    match = re.search(r'var\(\s*"OVERRIDE_API_PRODUCTION".*?\)', source, re.S)

    assert match is not None, "OVERRIDE_API_PRODUCTION is no longer generated"
    assert '"true"' not in match.group(0), (
        "the generator defaults the generic /api/* proxy on, so a generated "
        ".env opens it as soon as it reaches a production build"
    )


@pytest.mark.parametrize("required", ["POSTGRES_HOST", "REDIS_HOST"])
def test_the_example_still_documents_the_variables_it_should(required: str):
    """Guard against the IP cleanup accidentally deleting the entries."""
    assert f"{required}=" in ENV_EXAMPLE.read_text(encoding="utf-8")


DOCS = REPO_ROOT / "docs" / "env-variables.md"

# Variable names the document used to claim the services read. They do not:
# every service takes POSTGRES_* parts and assembles its own DSN, and only
# agent-service and rag-service use a bare PORT (user-service uses SERVICE_PORT).
DOC_ROW = re.compile(r"^\|\s*`([A-Z0-9_]+)`")


def _documented_variables() -> set[str]:
    return {
        match.group(1)
        for line in DOCS.read_text(encoding="utf-8").splitlines()
        if (match := DOC_ROW.match(line))
    }


def test_the_document_does_not_invent_a_database_url_variable():
    """No service reads a bare DATABASE_URL; documenting one sent people to
    configure a variable nothing consumes, and the service then fell back to
    its defaults — which is how a silent misconfiguration starts."""
    assert "DATABASE_URL" not in _documented_variables()


def test_the_document_names_the_connection_parts_the_services_actually_read():
    documented = _documented_variables()

    for part in ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB"):
        assert any(part in name for name in documented) or part in DOCS.read_text(
            encoding="utf-8"
        ), f"{part} is not documented anywhere"
