.PHONY: docker-config docker-build-services docker-verify hooks-install quality-staged quality-push quality-all

docker-config:
	docker compose -f configs/docker-compose-dev.yml config >/tmp/agentic-dev-compose.yml
	docker compose -f configs/docker-compose-prod.yml config >/tmp/agentic-prod-compose.yml

docker-build-services:
	docker compose -f configs/docker-compose-dev.yml build agent-service user-service rag-service tools-service

docker-verify: docker-config docker-build-services

hooks-install:
	bash scripts/install-git-hooks.sh

quality-staged:
	bash scripts/quality/check.sh staged

quality-push:
	bash scripts/quality/check.sh push

quality-all:
	bash scripts/quality/check.sh all
