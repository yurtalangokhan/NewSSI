.PHONY: docker-config docker-build-services docker-verify hooks-install validate-services validate quality-staged quality-push quality-all

PYTHON_SERVICES ?= agent-service user-service rag-service tools-service

docker-config:
	docker compose -f configs/docker-compose-dev.yml config >/tmp/agentic-dev-compose.yml
	docker compose -f configs/docker-compose-prod.yml config >/tmp/agentic-prod-compose.yml

docker-build-services:
	docker compose -f configs/docker-compose-dev.yml build $(PYTHON_SERVICES)

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
