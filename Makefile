SHELL := /bin/bash
PY := .venv/bin/python
COMPOSE := docker compose --env-file .env -f infra/docker-compose.yml

.PHONY: help check-tools check-dev check-docker env venv install up down logs migrate ingest-ppr gazetteer geocode enrich benchmarks aggregate pipeline osm-extract basemap terrain geocoder test test-db lint format typecheck api-types e2e e2e-stack e2e-static ci

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

DB_ROLE_PASSWORDS := APP_DB_PASSWORD PIPELINE_DB_PASSWORD TILES_DB_PASSWORD

env: ## Create .env from .env.example with random local secrets (never overwrites; adds new ones)
	@if test -f .env; then \
	  echo ".env exists, leaving its values alone"; \
	  for v in $(DB_ROLE_PASSWORDS); do \
	    grep -q "^$$v=." .env || { grep -v "^$$v=" .env > .env.tmp; mv .env.tmp .env; \
	      echo "$$v=$$(openssl rand -hex 16)" >> .env; echo "added $$v (run make migrate)"; }; \
	  done; \
	else \
	  pw=$$(openssl rand -hex 16); \
	  sed -e "s|^SESSION_SECRET=.*|SESSION_SECRET=$$(openssl rand -hex 32)|" \
	      -e "s|^CSRF_SECRET=.*|CSRF_SECRET=$$(openssl rand -hex 32)|" \
	      -e "s|^IP_HASH_SALT=.*|IP_HASH_SALT=$$(openssl rand -hex 16)|" \
	      -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$$pw|" \
	      -e "s|^APP_DB_PASSWORD=.*|APP_DB_PASSWORD=$$(openssl rand -hex 16)|" \
	      -e "s|^PIPELINE_DB_PASSWORD=.*|PIPELINE_DB_PASSWORD=$$(openssl rand -hex 16)|" \
	      -e "s|^TILES_DB_PASSWORD=.*|TILES_DB_PASSWORD=$$(openssl rand -hex 16)|" \
	      -e "s|CHANGE_ME|$$pw|g" .env.example > .env; \
	  echo "wrote .env"; \
	fi

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

# Migrations and role passwords run as the database owner (POSTGRES_USER); the api container
# itself signs in as ppr_app and never sees the owner's password (migration 0014).
migrate: ## Apply migrations, let the service roles sign in, sync roles/permissions (in the api container)
	@set -a; source .env; set +a; \
	owner="postgresql+psycopg://$${POSTGRES_USER:-pprmap}:$${POSTGRES_PASSWORD}@db:5432/$${POSTGRES_DB:-pprmap}"; \
	$(COMPOSE) exec -e DATABASE_URL="$$owner" api alembic upgrade head && \
	$(COMPOSE) exec -e DATABASE_URL="$$owner" -e APP_DB_PASSWORD="$$APP_DB_PASSWORD" \
	  -e PIPELINE_DB_PASSWORD="$$PIPELINE_DB_PASSWORD" -e TILES_DB_PASSWORD="$$TILES_DB_PASSWORD" \
	  api python -m app.cli db-roles
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

gazetteer: ## Build the local street gazetteer: OSM streets, estates, addresses; DHLGH estates (~8 min)
	@test -f $(OSM_PBF) || $(MAKE) osm-extract
	set -a; source .env; set +a; .venv/bin/ppr gazetteer

geocode: ## Geocode new properties (needs `make geocoder`; the first full run takes 1-2 h)
	set -a; source .env; set +a; .venv/bin/ppr geocode

enrich: ## Reload stops, amenities and deprivation; recompute vicinity values
	set -a; source .env; set +a; .venv/bin/ppr enrich

benchmarks: ## Load the CSO price index and recompute the estimate's calibration (D-053)
	set -a; source .env; set +a; .venv/bin/ppr ingest cso_rppi

aggregate: ## Rebuild area stats, price hexes and hover summaries
	set -a; source .env; set +a; .venv/bin/ppr aggregate

pipeline: ingest-ppr gazetteer geocode enrich benchmarks aggregate ## The monthly run, in order

OSM_PBF := data/osm/ireland-and-northern-ireland-latest.osm.pbf
OSM_URL := https://download.geofabrik.de/europe/ireland-and-northern-ireland-latest.osm.pbf

osm-extract: ## Download the Geofabrik Ireland OSM extract (~400 MB) and check its md5
	mkdir -p data/osm
	curl -sSL --fail -A "ppr-map/0.1" -o $(OSM_PBF).part $(OSM_URL)
	@want=$$(curl -sSL --fail $(OSM_URL).md5 | cut -d' ' -f1); \
	got=$$( (md5sum $(OSM_PBF).part 2>/dev/null || md5 -r $(OSM_PBF).part) | cut -d' ' -f1); \
	[ -n "$$want" ] && [ "$$want" = "$$got" ] || { echo "md5 mismatch, keeping $(OSM_PBF).part"; exit 1; }
	mv $(OSM_PBF).part $(OSM_PBF)

# Basemap (D-005): an Ireland extract of a pinned Protomaps daily build, and the fonts and
# sprites its style needs, served by Caddy at /basemap/. Nothing is fetched from Protomaps
# at view time.
PMTILES_VERSION := 1.31.2
BASEMAP_BUILD := 20260926
BASEMAP_ASSETS_REF := 028c18f713baecad011301ff7a69acc39bcc2ae7
BASEMAP_BBOX := -10.8,51.2,-5.3,55.5
# Terrain (D-045): Mapterhorn's terrarium tiles (Copernicus GLO-30 over Ireland). z11 is
# about 23 m a pixel here, already finer than the 30 m source, and 55 MB.
TERRAIN_URL := https://download.mapterhorn.com/planet.pmtiles
PMTILES := .tools/pmtiles

# Release files: go-pmtiles-<v>_Darwin_<arch>.zip, but go-pmtiles_<v>_Linux_<arch>.tar.gz.
$(PMTILES):
	mkdir -p .tools
	@arch=$$(uname -m | sed 's/aarch64/arm64/'); \
	base=https://github.com/protomaps/go-pmtiles/releases/download/v$(PMTILES_VERSION); \
	case "$$(uname -s)" in \
	  Darwin) curl -sSL --fail -o .tools/pmtiles.zip $$base/go-pmtiles-$(PMTILES_VERSION)_Darwin_$$arch.zip \
	            && cd .tools && unzip -oq pmtiles.zip pmtiles && rm pmtiles.zip ;; \
	  Linux) curl -sSL --fail $$base/go-pmtiles_$(PMTILES_VERSION)_Linux_$$arch.tar.gz | tar -xz -C .tools pmtiles ;; \
	  *) echo "make basemap supports macOS and Linux"; exit 1 ;; \
	esac

basemap: $(PMTILES) terrain ## Download the Ireland basemap (~600 MB), terrain, fonts and sprites
	mkdir -p data/basemap
	$(PMTILES) extract https://build.protomaps.com/$(BASEMAP_BUILD).pmtiles data/basemap/ireland.pmtiles --bbox=$(BASEMAP_BBOX) --maxzoom=15
	curl -sSL --fail -o data/basemap/assets.tar.gz https://github.com/protomaps/basemaps-assets/archive/$(BASEMAP_ASSETS_REF).tar.gz
	rm -rf data/basemap/assets && mkdir -p data/basemap/assets
	tar -xzf data/basemap/assets.tar.gz -C data/basemap/assets --strip-components=1 \
	  "basemaps-assets-$(BASEMAP_ASSETS_REF)/fonts/Noto Sans Regular" \
	  "basemaps-assets-$(BASEMAP_ASSETS_REF)/fonts/Noto Sans Medium" \
	  "basemaps-assets-$(BASEMAP_ASSETS_REF)/fonts/Noto Sans Italic" \
	  "basemaps-assets-$(BASEMAP_ASSETS_REF)/fonts/OFL.txt" \
	  "basemaps-assets-$(BASEMAP_ASSETS_REF)/sprites/v4"
	rm data/basemap/assets.tar.gz

terrain: $(PMTILES) ## Download Ireland's elevation tiles for hill shading and the 3D view (~55 MB)
	mkdir -p data/basemap
	$(PMTILES) extract $(TERRAIN_URL) data/basemap/terrain.pmtiles --bbox=$(BASEMAP_BBOX) --maxzoom=11

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

api-types: ## Regenerate frontend/openapi.json and the TypeScript API types from the backend
	cd backend && ../.venv/bin/python -m app.cli openapi > ../frontend/openapi.json
	cd frontend && npm run api:types

e2e: ## Playwright smoke tests over every route
	cd frontend && npm run test:e2e

e2e-stack: ## Playwright against the running stack with real data (make up + pipeline + basemap)
	cd frontend && E2E_STACK=1 npx playwright test

e2e-static: ## The same tests against the static export, as Vercel serves the preview
	cd frontend && STATIC_EXPORT=1 npm run build && E2E_STATIC=1 npm run test:e2e

ci: lint typecheck test ## What CI runs (minus the database and e2e jobs)
