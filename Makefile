SHELL := /bin/bash
PY := .venv/bin/python
COMPOSE := docker compose --env-file .env -f infra/docker-compose.yml

.PHONY: help check-tools check-dev check-docker env venv install up down logs migrate ingest-ppr osm-extract geocoder test test-db lint format typecheck e2e e2e-pages ci

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

env: ## Create .env from .env.example with random local secrets (never overwrites)
	@test -f .env && echo ".env exists, leaving it alone" || { \
	  pw=$$(openssl rand -hex 16); \
	  sed -e "s|^SESSION_SECRET=.*|SESSION_SECRET=$$(openssl rand -hex 32)|" \
	      -e "s|^CSRF_SECRET=.*|CSRF_SECRET=$$(openssl rand -hex 32)|" \
	      -e "s|^IP_HASH_SALT=.*|IP_HASH_SALT=$$(openssl rand -hex 16)|" \
	      -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$$pw|" \
	      -e "s|CHANGE_ME|$$pw|g" .env.example > .env; \
	  echo "wrote .env"; }

venv: ## Python virtualenv with backend + pipeline (editable) and dev tools
	python3.12 -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -e "backend[dev]" -e "pipeline[dev]"

check-tools: check-dev check-docker ## Check that Python 3.12, Node 22+ and Docker are installed

check-dev:
	@ok=1; \
	command -v python3.12 >/dev/null || { echo "missing: Python 3.12 (python.org installer)"; ok=0; }; \
	command -v node >/dev/null && [ "$$(node -p 'process.versions.node.split(".")[0]')" -ge 22 ] \
	  || { echo "missing: Node.js 22 LTS or newer (nodejs.org; open a new terminal after installing)"; ok=0; }; \
	[ $$ok = 1 ] || { echo "Install the missing tools, then rerun."; exit 1; }

check-docker:
	@command -v docker >/dev/null || { echo "missing: Docker (Docker Desktop or OrbStack), needed for make up"; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "Docker is installed but not running: open Docker Desktop or OrbStack"; exit 1; }

install: check-dev venv ## venv + frontend node_modules + Playwright browser
	cd frontend && npm ci && npx playwright install chromium

up: check-docker env ## Start the local stack (http://localhost:8080)
	$(COMPOSE) up -d --build

down: ## Stop the local stack (including the geocoder, if running)
	$(COMPOSE) --profile geocoder down

logs: ## Follow logs
	$(COMPOSE) logs -f

migrate: ## Apply migrations and sync roles/permissions (inside the api container)
	$(COMPOSE) exec api alembic upgrade head
	$(COMPOSE) exec api python -m app.cli sync-permissions

lint: ## Lint everything
	cd backend && ../.venv/bin/ruff check . && ../.venv/bin/ruff format --check .
	cd pipeline && ../.venv/bin/ruff check . && ../.venv/bin/ruff format --check .
	cd frontend && npm run lint && npm run format:check

format: ## Auto-format everything
	cd backend && ../.venv/bin/ruff format . && ../.venv/bin/ruff check --fix .
	cd pipeline && ../.venv/bin/ruff format . && ../.venv/bin/ruff check --fix .
	cd frontend && npm run format

typecheck: ## mypy (strict) + tsc
	cd backend && ../.venv/bin/mypy app
	cd pipeline && ../.venv/bin/mypy src
	cd frontend && npm run typecheck

ingest-ppr: ## Download the Property Price Register and load it (needs `make up` + `make migrate`)
	set -a; source .env; set +a; .venv/bin/ppr ingest ppr

OSM_PBF := data/osm/ireland-and-northern-ireland-latest.osm.pbf
OSM_URL := https://download.geofabrik.de/europe/ireland-and-northern-ireland-latest.osm.pbf

osm-extract: ## Download the Geofabrik Ireland OSM extract (~400 MB) and check its md5
	mkdir -p data/osm
	curl -sSL --fail -A "ppr-map/0.1" -o $(OSM_PBF).part $(OSM_URL)
	@want=$$(curl -sSL --fail $(OSM_URL).md5 | cut -d' ' -f1); \
	got=$$( (md5sum $(OSM_PBF).part 2>/dev/null || md5 -r $(OSM_PBF).part) | cut -d' ' -f1); \
	[ -n "$$want" ] && [ "$$want" = "$$got" ] || { echo "md5 mismatch, keeping $(OSM_PBF).part"; exit 1; }
	mv $(OSM_PBF).part $(OSM_PBF)

geocoder: check-docker ## Start self-hosted Nominatim (first run imports Ireland: 1h+)
	@test -f $(OSM_PBF) || $(MAKE) osm-extract
	$(COMPOSE) --profile geocoder up -d nominatim

test: ## Unit tests (no database needed)
	cd backend && ../.venv/bin/pytest -q
	cd pipeline && ../.venv/bin/pytest -q
	cd frontend && npm test

test-db: ## Backend and pipeline tests including live PostGIS checks (needs `make up`)
	set -a; source .env; set +a; cd backend && ../.venv/bin/pytest -q
	set -a; source .env; set +a; cd pipeline && ../.venv/bin/pytest -q

e2e: ## Playwright smoke tests over every route
	cd frontend && npm run test:e2e

e2e-pages: ## The same tests against the GitHub Pages static export, under /ppr-map
	cd frontend && STATIC_EXPORT=1 PAGES_BASE_PATH=/ppr-map npm run build && E2E_BASE_PATH=/ppr-map npm run test:e2e

ci: lint typecheck test ## What CI runs (minus the database and e2e jobs)
