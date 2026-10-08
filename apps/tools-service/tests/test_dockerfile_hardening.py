"""The image must be reproducible and non-root. Spec TS-12.

uv.lock existed on disk but was never copied into the image, so fastmcp
(pinned >=2.0.0 in pyproject.toml) silently drifted to whatever version
`uv pip install --system fastmcp` resolved at build time (3.1.0, a major
version away). The image also shelled a `curl | sh` to install the Docker
CLI, ran as root, and had no HEALTHCHECK.
"""

from pathlib import Path

import pytest

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


@pytest.fixture
def dockerfile() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def test_dependencies_are_installed_from_the_lock_file(dockerfile):
    assert "uv sync --frozen" in dockerfile
    assert "COPY apps/tools-service/uv.lock" in dockerfile


def test_no_unpinned_uv_pip_install(dockerfile):
    assert "uv pip install --system" not in dockerfile


def test_no_curl_pipe_shell(dockerfile):
    assert "| sh" not in dockerfile
    assert "| bash" not in dockerfile


def test_docker_cli_is_not_installed(dockerfile):
    assert "get.docker.com" not in dockerfile
    assert "docker.com" not in dockerfile


def test_runs_as_a_non_root_user(dockerfile):
    assert "USER 10001" in dockerfile


def test_workspace_is_not_world_writable(dockerfile):
    assert "chmod 777" not in dockerfile


def test_healthcheck_is_defined(dockerfile):
    assert "HEALTHCHECK" in dockerfile


def test_every_local_path_dependency_is_copied_before_sync(dockerfile):
    """Every [tool.uv.sources] path entry in pyproject.toml must be present
    in the build context before `uv sync --frozen` runs, or the sync fails
    (or, worse, silently resolves a different version from PyPI)."""
    for package in (
        "config-manager",
        "localization",
        "idempotency",
        "error-contract",
        "metrics",
        "security",
    ):
        assert f"packages/{package}/" in dockerfile, f"missing COPY for {package}"


def test_unzip_is_still_installed_for_inspect_jar(dockerfile):
    """java_tools.inspect_jar shells out to `unzip -p ... MANIFEST.MF`."""
    assert "unzip" in dockerfile
