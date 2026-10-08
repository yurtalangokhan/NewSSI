"""The web image is built from the same configuration file as every other build.

`next build` evaluates `src/lib/env` (zod validation of the whole server and
client schema) and `next.config.js` (`requireEnv`), and inlines every
`NEXT_PUBLIC_*` value into the browser bundle. Locally `npm run build` gets that
configuration from `config_manager` reading `configs/.env`. The image build has
neither, so Compose hands the file in as the BuildKit secret `web_env`, which
the builder stage mounts as `/app/.env` for the `next build` step only: Next.js
reads it like any `.env` file, and a secret mount never lands in a layer. But
`next build` copies the `.env` files it loaded into `.next/standalone`, which
the runner stage copies wholesale, so the same step strips that copy.

Two things silently defeat that: a builder-stage `ENV NEXT_PUBLIC_X=${...}`
line (an unset build arg becomes the empty string, and a value already in the
environment wins over the file), and a Compose file that forgets the secret or
one of the build args the Dockerfile turns into `ENV` without a default (the
same empty string, shadowing the file).
"""

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "apps" / "web" / "Dockerfile"
COMPOSE_FILES = [
    "deploy/docker/docker-compose-dev.yml",
    "deploy/docker/docker-compose-prod.yml",
]
ENV_SECRET = "web_env"
ENV_FILE = "../../configs/.env"


def _builder_stage() -> str:
    text = DOCKERFILE.read_text(encoding="utf-8")
    return text[text.index("FROM base AS builder") : text.index("FROM base AS runner")]


def _build_step() -> str:
    """The `RUN ... next build` instruction with its continuation lines joined."""
    stage = _builder_stage().replace("\\\n", " ")
    steps = [
        line for line in stage.splitlines() if line.startswith("RUN ") and "next build" in line
    ]
    assert len(steps) == 1, steps
    return steps[0]


def _args_turned_into_env_without_default() -> list[str]:
    stage = _builder_stage()
    names = re.findall(r"^ARG ([A-Z_]+)$", stage, flags=re.MULTILINE)
    return [name for name in names if f"ENV {name}=${{{name}}}" in stage]


def _compose(relative_path: str) -> dict:
    return yaml.safe_load((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def test_next_build_mounts_the_shared_env_file_as_a_build_secret():
    assert f"--mount=type=secret,id={ENV_SECRET},target=/app/.env" in _build_step(), (
        "apps/web/Dockerfile builds without configs/.env, so `next build` fails on the "
        "first required key (NEXT_PUBLIC_POSTHOG_HOST) and would inline nothing public"
    )


def test_next_build_strips_the_env_file_copy_from_the_standalone_output():
    assert "rm -f .next/standalone/.env .next/standalone/.env.*" in _build_step(), (
        "`next build` copies the .env files it loaded into .next/standalone, which the "
        "runner stage copies wholesale: without the rm the image ships configs/.env"
    )


def test_the_builder_bakes_no_public_env_that_would_shadow_the_env_file():
    baked = [
        line
        for line in _builder_stage().splitlines()
        if line.startswith(("ARG NEXT_PUBLIC_", "ENV NEXT_PUBLIC_"))
    ]

    assert not baked, (
        "an unset build arg becomes the empty string in these ENV lines, and Next.js "
        f"keeps a value already in the environment over /app/.env: {baked}"
    )


@pytest.mark.parametrize("relative_path", COMPOSE_FILES)
def test_compose_hands_the_env_file_to_the_web_build_as_the_secret(relative_path: str):
    compose = _compose(relative_path)

    assert compose["services"]["web"]["build"].get("secrets") == [ENV_SECRET], relative_path
    assert compose.get("secrets", {}).get(ENV_SECRET) == {"file": ENV_FILE}, relative_path


@pytest.mark.parametrize("relative_path", COMPOSE_FILES)
def test_compose_passes_every_build_arg_the_dockerfile_turns_into_env(relative_path: str):
    args = _compose(relative_path)["services"]["web"]["build"].get("args", {})
    missing = [name for name in _args_turned_into_env_without_default() if name not in args]

    assert not missing, (
        f"{relative_path} leaves {missing} unset: the Dockerfile's ENV turns an unset build "
        "arg into the empty string, which shadows the value in configs/.env"
    )
