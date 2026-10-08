.PHONY: packages-test packages-lint packages-typecheck governance-static governance-contract governance-scan i18n-check env-check env-test third-party-up gateway-reload ollama-models prod-up stack-up docker-config docker-build-services docker-build-apps docker-smoke-agent-service docker-verify hooks-install validate-services validate quality-staged quality-push quality-all architecture-check quality-score

PYTHON_SERVICES ?= agent-service user-service rag-service tools-service
SHARED_PACKAGES ?= config-manager error-contract idempotency localization metrics observability security
APP_SERVICES ?= $(PYTHON_SERVICES) web
APP_IMAGE_TAG ?= latest
QUALITY_SCORE_MIN ?= 80
PYTHON ?= python3


third-party-up:
	docker compose --env-file configs/.env -f deploy/docker/docker-compose-services.yml up -d

# The Gateway policy inventory is bind-mounted as a single file, so a running
# container keeps the copy it mounted when it was created. Recreate the Gateway
# after regenerating configs/apisix/gateway-policies.json; a plain restart keeps
# the stale inventory and can fail to mount at all.
gateway-reload:
	docker compose --env-file configs/.env -f deploy/docker/docker-compose-services.yml up -d --force-recreate --no-deps apisix

ollama-models:
	scripts/pull_ollama_models.sh

prod-up:
	APP_IMAGE_TAG=$(APP_IMAGE_TAG) docker compose --env-file configs/.env -f deploy/docker/docker-compose-prod.yml up -d

stack-up:
	$(MAKE) third-party-up
	$(MAKE) ollama-models
	$(MAKE) prod-up

docker-config:
	docker compose --env-file configs/.env -f deploy/docker/docker-compose-services.yml config >/tmp/agentic-services-compose.yml
	APP_IMAGE_TAG=$(APP_IMAGE_TAG) docker compose --env-file configs/.env -f deploy/docker/docker-compose-dev.yml config >/tmp/agentic-dev-compose.yml
	APP_IMAGE_TAG=$(APP_IMAGE_TAG) docker compose --env-file configs/.env -f deploy/docker/docker-compose-prod.yml config >/tmp/agentic-prod-compose.yml

env-check:
		PYTHONPATH=packages/config-manager/src $(PYTHON) -m config_manager.manager check

env-test:
		PYTHONPATH=packages/config-manager/src $(PYTHON) -m unittest scripts.tests.test_env_manager scripts.tests.test_central_env

docker-build-services:
	APP_IMAGE_TAG=$(APP_IMAGE_TAG) docker compose --env-file configs/.env -f deploy/docker/docker-compose-dev.yml build $(PYTHON_SERVICES)

docker-build-apps:
	APP_IMAGE_TAG=$(APP_IMAGE_TAG) docker compose --env-file configs/.env -f deploy/docker/docker-compose-dev.yml build $(APP_SERVICES)

docker-smoke-agent-service:
	docker run --rm --entrypoint python agentic-ai-platform/agent-service:$(APP_IMAGE_TAG) -c "import app"

docker-verify: docker-config docker-build-apps

hooks-install:
	bash scripts/install-git-hooks.sh

validate-services:
	make -C apps/agent-service validate
	make -C apps/rag-service validate
	make -C apps/user-service validate
	make -C apps/tools-service validate

validate: quality-all docker-verify

quality-staged:
	bash scripts/validate-commit.sh

quality-push:
	bash scripts/validate-push.sh

quality-all:
	bash scripts/quality/check.sh all

architecture-check:
	python3 scripts/quality/check_architecture.py --all

quality-score:
	python3 scripts/quality/score.py --all

# ---------------------------------------------------------------------------
# Governance gate
#
# `governance-scan` is what CI runs on every merge request. It is deliberately
# cheap and infrastructure-free: no database, no Keycloak, no network. Anything
# needing a live dependency belongs in `validate`, not here.
# ---------------------------------------------------------------------------

packages-test:
	@for pkg in $(SHARED_PACKAGES); do \
		echo "==> packages/$$pkg"; \
		( cd packages/$$pkg && uv run --quiet pytest -q ) || exit 1; \
	done

packages-lint:
	@for pkg in $(SHARED_PACKAGES); do \
		echo "==> packages/$$pkg"; \
		( cd packages/$$pkg && uv run --quiet ruff check . ) || exit 1; \
	done

# The shared packages do not each carry a mypy install; the typecheck runs from
# agent-service's venv, which already pins mypy and the pydantic plugin, with
# the same lenient error codes the services use.
#
# Enforcement is limited to the packages this spec touched (idempotency,
# metrics): the other packages carry pre-existing findings owned by other
# work streams, and blocking on them here would couple this gate to someone
# else's backlog. Their findings are printed, not enforced.
PACKAGES_TYPECHECK_ENFORCED ?= idempotency metrics
PACKAGES_TYPECHECK_REPORTED ?= $(filter-out $(PACKAGES_TYPECHECK_ENFORCED),$(SHARED_PACKAGES))

packages-typecheck:
	@for pkg in $(PACKAGES_TYPECHECK_REPORTED); do \
		echo "==> packages/$$pkg (report-only)"; \
		apps/agent-service/.venv/bin/mypy packages/$$pkg/src/ \
			--ignore-missing-imports --explicit-package-bases --allow-redefinition \
			--disable-error-code import-untyped --disable-error-code no-redef \
			--disable-error-code attr-defined --disable-error-code assignment \
			--disable-error-code arg-type || true; \
	done
	@for pkg in $(PACKAGES_TYPECHECK_ENFORCED); do \
		echo "==> packages/$$pkg"; \
		apps/agent-service/.venv/bin/mypy packages/$$pkg/src/ \
			--ignore-missing-imports --explicit-package-bases --allow-redefinition \
			--disable-error-code import-untyped --disable-error-code no-redef \
			--disable-error-code attr-defined --disable-error-code assignment \
			--disable-error-code arg-type || exit 1; \
	done

# Repository-level rules: compose healthchecks and isolation, resilience policy
# keys, the architecture catalog, gateway exposure, root project metadata.
governance-static:
	@echo "==> repository governance rules"
	@apps/agent-service/.venv/bin/python -m pytest scripts/tests -q

# API and observability contract, checked against each service's real
# application object using that service's own interpreter.
governance-contract:
	@apps/agent-service/.venv/bin/python scripts/governance/check_service_contract.py \
		--root apps/agent-service --src src --app app:app --warmup /api/v1/health/
	@apps/user-service/.venv/bin/python scripts/governance/check_service_contract.py \
		--root apps/user-service --src src --app main:create_app\(\) --warmup /api/v1/health/
	@apps/rag-service/.venv/bin/python scripts/governance/check_service_contract.py \
		--root apps/rag-service --app src.server:APP --warmup /api/v1/health
	@apps/tools-service/.venv/bin/python scripts/governance/check_service_contract.py \
		--root apps/tools-service --app server:app --warmup /health

# Locale-file parity, placeholder-consistency, and used/defined key drift
# across every service's en.json/tr.json -- reads only local files, no
# database or network, so it belongs in the same cheap/infra-free tier as
# the rest of the governance gate.
i18n-check:
	@echo "==> i18n translation parity check"
	@cd packages/localization && uv run --quiet python -c "\
import sys; \
from pathlib import Path; \
from localization.checker import check_missing_translations; \
sys.exit(0 if check_missing_translations(Path('$(CURDIR)')) else 1)"

governance-scan: packages-lint packages-test governance-static governance-contract i18n-check
	@echo "==> Governance scan passed"
