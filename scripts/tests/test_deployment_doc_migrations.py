"""``docs/deployment.md`` names the migrations an upgrade applies.

A cited revision must exist in the service it is attributed to: the numbers
drift when migrations are renumbered on a merge, and an operator who applies
the wrong one gets a silent no-op.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT_DOC = ROOT / "docs" / "deployment.md"
MIGRATION_VERSIONS = {
    "agent-service": ROOT / "apps/agent-service/src/infrastructure/db/migrations/versions",
    "user-service": ROOT / "apps/user-service/src/core/database/migrations/versions",
}
CITATION = re.compile(r"(agent-service|user-service) migrations? `(\d{4})`(?: and `(\d{4})`)?")


def _cited_revisions() -> dict[str, set[str]]:
    cited: dict[str, set[str]] = {service: set() for service in MIGRATION_VERSIONS}
    for service, first, second in CITATION.findall(DEPLOYMENT_DOC.read_text(encoding="utf-8")):
        cited[service].update(revision for revision in (first, second) if revision)
    return cited


def test_deployment_doc_cites_migrations_that_exist():
    cited = _cited_revisions()
    assert cited["agent-service"] and cited["user-service"], "the connector upgrade names both"
    for service, revisions in cited.items():
        files = MIGRATION_VERSIONS[service].glob("[0-9][0-9][0-9][0-9]_*.py")
        present = {path.name[:4] for path in files}
        missing = sorted(revisions - present)
        assert not missing, f"{service}: {missing} not in migrations/versions"
