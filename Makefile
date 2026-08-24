.PHONY: env-check env-init env-test third-party-up ollama-models prod-up stack-up docker-config docker-build-services docker-build-apps docker-verify hooks-install validate-services validate quality-staged quality-push quality-all

PYTHON_SERVICES ?= agent-service user-service rag-service tools-service
APP_SERVICES ?= $(PYTHON_SERVICES) web
APP_IMAGE_TAG ?= latest

third-party-up:
	docker compose --env-file configs/.env -f configs/docker-compose-services.yml up -d

ollama-models:
	scripts/pull_ollama_models.sh

prod-up:
	APP_IMAGE_TAG=$(APP_IMAGE_TAG) docker compose --env-file configs/.env -f configs/docker-compose-prod.yml up -d

stack-up:
	$(MAKE) third-party-up
	$(MAKE) ollama-models
	$(MAKE) prod-up

docker-config:
	docker compose --env-file configs/.env -f configs/docker-compose-services.yml config >/tmp/agentic-services-compose.yml
	APP_IMAGE_TAG=$(APP_IMAGE_TAG) docker compose --env-file configs/.env -f configs/docker-compose-dev.yml config >/tmp/agentic-dev-compose.yml
	APP_IMAGE_TAG=$(APP_IMAGE_TAG) docker compose --env-file configs/.env -f configs/docker-compose-prod.yml config >/tmp/agentic-prod-compose.yml

env-check:
	python scripts/env_manager.py check

env-init:
	python scripts/env_manager.py init

env-test:
	python -m unittest scripts.tests.test_env_manager

docker-build-services:
	APP_IMAGE_TAG=$(APP_IMAGE_TAG) docker compose --env-file configs/.env -f configs/docker-compose-dev.yml build $(PYTHON_SERVICES)

docker-build-apps:
	APP_IMAGE_TAG=$(APP_IMAGE_TAG) docker compose --env-file configs/.env -f configs/docker-compose-dev.yml build $(APP_SERVICES)

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
	bash scripts/quality/check.sh staged

quality-push:
	bash scripts/quality/check.sh push

quality-all:
	bash scripts/quality/check.sh all
