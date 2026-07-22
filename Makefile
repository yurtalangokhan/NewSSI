.PHONY: env-check env-init env-test docker-config docker-build-services docker-verify hooks-install validate-services validate quality-staged quality-push quality-all

PYTHON_SERVICES ?= agent-service user-service rag-service tools-service

docker-config:
	docker compose --env-file configs/.env -f configs/docker-compose-services.yml config >/tmp/agentic-services-compose.yml
	docker compose --env-file configs/.env -f configs/docker-compose-dev.yml config >/tmp/agentic-dev-compose.yml
	docker compose --env-file configs/.env -f configs/docker-compose-prod.yml config >/tmp/agentic-prod-compose.yml

env-check:
	python scripts/env_manager.py check

env-init:
	python scripts/env_manager.py init

env-test:
	python -m unittest scripts.tests.test_env_manager

docker-build-services:
	docker compose --env-file configs/.env -f configs/docker-compose-dev.yml build $(PYTHON_SERVICES)

docker-verify: docker-config docker-build-services

hooks-install:
	bash scripts/install-git-hooks.sh

validate-services:
	make -C apps/agent-service validate
	make -C apps/rag-service validate
	make -C apps/user-service validate
	make -C apps/tools-service validate

validate: quality-all docker-verify

quality-staged:
	bash scripts/quality/check.sh staged

quality-push:
	bash scripts/quality/check.sh push

quality-all:
	bash scripts/quality/check.sh all
