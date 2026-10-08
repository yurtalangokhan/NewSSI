"""Every service image must be reproducible and run as a non-root user.

tools-service was hardened in an earlier pass; the other three images were
left behind. They each regenerate `uv.lock` mid-build and then install with
`--frozen`, which makes the flag meaningless — the lock the image installs is
whatever resolved at build time, not the one that was reviewed. And with no
USER directive the application process is root inside the container, so any
code-execution bug starts with full container privileges.
"""

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

SERVICE_DOCKERFILES = [
    "apps/user-service/Dockerfile",
    "apps/rag-service/Dockerfile",
    "apps/agent-service/docker/Dockerfile.service",
    "apps/tools-service/Dockerfile",
]


def _instructions(relative_path: str) -> str:
    """The Dockerfile with comment lines removed.

    The comments explain why `uv lock` was taken out, so a naive substring
    search over the whole file matches its own rationale.
    """
    return "\n".join(
        line
        for line in (REPO_ROOT / relative_path).read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("#")
    )


@pytest.mark.parametrize("relative_path", SERVICE_DOCKERFILES)
def test_the_lock_file_is_not_regenerated_during_the_build(relative_path: str):
    dockerfile = _instructions(relative_path)

    assert "uv lock" not in dockerfile, (
        f"{relative_path} regenerates uv.lock at build time, which defeats "
        "the --frozen install that follows it"
    )


@pytest.mark.parametrize("relative_path", SERVICE_DOCKERFILES)
def test_dependencies_come_from_the_lock_file(relative_path: str):
    dockerfile = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    assert "uv sync --frozen" in dockerfile


@pytest.mark.parametrize("relative_path", SERVICE_DOCKERFILES)
def test_the_image_drops_to_a_non_root_user(relative_path: str):
    dockerfile = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    user_lines = [
        line.strip()
        for line in dockerfile.splitlines()
        if line.strip().startswith("USER ")
    ]

    assert user_lines, f"{relative_path} has no USER directive and runs as root"
    assert not user_lines[-1].endswith("root"), f"{relative_path} ends up as root"


def _path_sources(service_dir: Path) -> list[str]:
    """The repo-relative local packages `[tool.uv.sources]` pins, e.g. `packages/security`."""
    pyproject = tomllib.loads((service_dir / "pyproject.toml").read_text(encoding="utf-8"))
    sources = pyproject.get("tool", {}).get("uv", {}).get("sources", {})
    return sorted(
        (service_dir / source["path"]).resolve().relative_to(REPO_ROOT).as_posix()
        for source in sources.values()
        if "path" in source
    )


@pytest.mark.parametrize("relative_path", SERVICE_DOCKERFILES)
def test_every_local_package_the_lock_pins_is_copied_into_the_image(relative_path: str):
    service_dir = REPO_ROOT / Path(relative_path).parts[0] / Path(relative_path).parts[1]
    dockerfile = _instructions(relative_path)
    missing = [
        package for package in _path_sources(service_dir) if f"COPY {package}/" not in dockerfile
    ]

    assert not missing, (
        f"{relative_path} never copies {', '.join(missing)} although "
        f"{service_dir.relative_to(REPO_ROOT).as_posix()}/pyproject.toml pins them as path "
        "sources, so `uv sync --frozen` fails with 'Distribution not found'"
    )


def test_the_web_image_installs_with_the_npm_major_that_wrote_the_lock():
    dockerfile = _instructions("apps/web/Dockerfile")

    assert "RUN npm ci" in dockerfile
    before_npm_ci = dockerfile[: dockerfile.index("RUN npm ci")]
    assert "npm install -g npm@11" in before_npm_ci, (
        "apps/web/Dockerfile runs `npm ci` with the npm 10 of node:22-alpine, which builds "
        "a different ideal tree from the npm 11 lock file (it nests the optional peer "
        "@swc/helpers@0.5.23 under i18next-cli's and i18next-resources-for-ts' @swc/core) "
        "and rejects the lock as out of sync; install npm 11 before `npm ci`"
    )
