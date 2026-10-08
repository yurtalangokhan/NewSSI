"""Architectural test: Verify Infrastructure Layer Separation & Provider Disambiguation.

Enterprise Architecture Rule:
1. `src/core/` is a lightweight foundational kernel:
   It contains only configuration, exceptions, http, observability, security, types, utils.
   It MUST NOT contain ORM, repositories, database migrations (`infrastructure/db`) or LLM engine adapters (`infrastructure/llm`).
2. `src/infrastructure/` is the dedicated layer for persistence and external drivers:
   - `src/infrastructure/db/`: models, repositories, migrations, persistence_gateway.
   - `src/infrastructure/llm/`: LLM runtime adapters, LLM factory, embeddings.
3. `service/providers/` is disambiguated:
   - Inference adapters live in `infrastructure.llm.adapters`.
   - Provider management & credentials live in `service.model_providers`.
   - No ambiguous `providers` package exists at both layers.
4. `alembic.ini` and `Dockerfile.service` reflect the infrastructure layer.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def test_core_does_not_contain_db_or_llm():
    """Verify that core/ no longer contains db or llm directories."""
    assert not (SRC_DIR / "core" / "db").exists(), (
        "src/infrastructure/db must be moved to src/infrastructure/db"
    )
    assert not (SRC_DIR / "core" / "llm").exists(), (
        "src/infrastructure/llm must be moved to src/infrastructure/llm"
    )


def test_infrastructure_db_structure():
    """Verify that infrastructure/db contains models, repositories, migrations and persistence_gateway."""
    infra_db = SRC_DIR / "infrastructure" / "db"
    assert infra_db.exists(), "src/infrastructure/db must exist"
    assert (infra_db / "models").is_dir(), "src/infrastructure/db/models must exist"
    assert (infra_db / "repositories").is_dir(), "src/infrastructure/db/repositories must exist"
    assert (infra_db / "migrations").is_dir(), "src/infrastructure/db/migrations must exist"
    assert (infra_db / "persistence_gateway.py").is_file(), (
        "src/infrastructure/db/persistence_gateway.py must exist"
    )


def test_infrastructure_llm_structure():
    """Verify that infrastructure/llm contains adapters, llm.py, llm_factory.py, embeddings.py."""
    infra_llm = SRC_DIR / "infrastructure" / "llm"
    assert infra_llm.exists(), "src/infrastructure/llm must exist"
    assert (infra_llm / "adapters").is_dir(), "src/infrastructure/llm/adapters must exist"
    assert (infra_llm / "llm.py").is_file(), "src/infrastructure/llm/llm.py must exist"
    assert (infra_llm / "embeddings.py").is_file(), (
        "src/infrastructure/llm/embeddings.py must exist"
    )


def test_no_ambiguous_providers_package():
    """Verify that infrastructure/llm/providers and service/providers are disambiguated."""
    assert not (SRC_DIR / "core" / "llm" / "providers").exists(), (
        "infrastructure/llm/providers must not exist"
    )
    assert not (SRC_DIR / "service" / "providers").exists(), (
        "src/service/providers must be renamed to src/service/model_providers"
    )
    assert (SRC_DIR / "service" / "model_providers").exists(), (
        "src/service/model_providers must exist"
    )


def test_alembic_ini_script_location():
    """Verify that alembic.ini points to src/infrastructure/db/migrations."""
    alembic_ini = PROJECT_ROOT / "alembic.ini"
    assert alembic_ini.exists()
    content = alembic_ini.read_text(encoding="utf-8")
    assert "src/infrastructure/db/migrations" in content, (
        "alembic.ini script_location must point to src/infrastructure/db/migrations"
    )


def test_dockerfile_copies_infrastructure():
    """Verify that Dockerfile.service copies src/infrastructure/."""
    dockerfile = PROJECT_ROOT / "docker" / "Dockerfile.service"
    assert dockerfile.exists()
    content = dockerfile.read_text(encoding="utf-8")
    assert re.search(r"COPY apps/agent-service/src/infrastructure/ \./infrastructure/", content), (
        "Dockerfile.service must copy src/infrastructure/ to ./infrastructure/"
    )
