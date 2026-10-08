from pathlib import Path


def test_dockerfile_installs_shared_idempotency_package() -> None:
    """Spec TS-12 switched dependency installation from an explicit
    `uv pip install --system ... ./packages/idempotency` argument list
    to `uv sync --frozen`, which resolves every dependency (including this
    one) from pyproject.toml/uv.lock instead -- so the package still needs
    to be present in the build context (this COPY), just not named again
    on the install command line."""
    dockerfile = Path(__file__).parents[1] / "Dockerfile"
    dockerfile_text = dockerfile.read_text()

    assert "packages/idempotency/" in dockerfile_text
    assert "uv sync --frozen" in dockerfile_text
