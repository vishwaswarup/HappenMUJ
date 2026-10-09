# Run the whole HappenMUJ stack. `make help` lists targets.
API_PORT ?= 8000
WEB_PORT ?= 5173

.DEFAULT_GOAL := help
.PHONY: help install mongo mongo-local seed api web test lint

help:        ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

install:     ## python + node dependencies
	cd backend && uv sync --python 3.12
	cd happenmuj-frontend && npm install

mongo:       ## MongoDB replica set via Docker (transactions need a replica set)
	docker compose up -d

mongo-local: ## same, without Docker (needs a local mongod; port 27018)
	./scripts/local_mongo.sh

seed:        ## wipe and reseed the demo data (16 clubs, 40 events, demo logins)
	cd backend && .venv/bin/python -m app.seed --reset

api:         ## FastAPI on $(API_PORT)  (http://localhost:$(API_PORT)/docs)
	cd backend && .venv/bin/uvicorn app.main:app --reload --port $(API_PORT)

web:         ## Vite dev server on 5173, proxying /api to the API
	cd happenmuj-frontend && VITE_PROXY_TARGET=http://localhost:$(API_PORT) npm run dev -- --port $(WEB_PORT)

test:        ## backend tests (real MongoDB) + frontend typecheck, tests and build
	cd backend && .venv/bin/pytest -q
	cd happenmuj-frontend && npm run typecheck && npm test && npm run build

lint:        ## ruff
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
