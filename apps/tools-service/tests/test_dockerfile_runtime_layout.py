from pathlib import Path


def test_dockerfile_installs_shared_idempotency_package() -> None:
    dockerfile = Path(__file__).parents[1] / "Dockerfile"
    dockerfile_text = dockerfile.read_text()

    assert "COPY packages/idempotency-py/ packages/idempotency-py/" in dockerfile_text
    assert "./packages/idempotency-py" in dockerfile_text
