.PHONY: install dev-install run build start test test-ci lint format format-check typecheck validate docker-verify clean

install:
	npm ci --omit=dev

dev-install:
	npm ci

run:
	npm run dev

build:
	npm run build

start:
	npm run start

test:
	npm test

test-ci:
	npm run test:ci

lint:
	npm run lint

format:
	npm run format

format-check:
	npm run format:check

typecheck:
	npm run types:check

validate: lint typecheck test-ci

docker-verify:
	$(MAKE) -C ../.. docker-config
	$(MAKE) -C ../.. docker-build-apps APP_SERVICES=web

clean:
	rm -rf .next coverage
