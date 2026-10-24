.PHONY: test lint build run clean help docker-login docker-build docker-push docker-deploy up down logs db-dump db-load db-dump-load db-clean

PYTHON := .venv/bin/python
VERSION := $(shell cat VERSION)
GHCR_REPO := ghcr.io/nachokruss/qbittorrent-stats

help: ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

test: ## Run all tests with pytest
	$(PYTHON) -m pytest tests/ -v

test-cov: ## Run tests with coverage report
	$(PYTHON) -m pytest tests/ -v --cov=collector --cov-report=term-missing

lint: ## Run code style and quality checks
	$(PYTHON) -m py_compile collector/*.py
	$(PYTHON) -m py_compile tests/*.py

build: ## Build the local Docker image
	docker build -t qbittorrent-stats:latest .

docker-login: ## Log in to GitHub Container Registry (reads token from .docker-token file)
	@ [ -f .docker-token ] || { echo "Error: .docker-token file not found. Create it with your GHCR personal access token."; exit 1; }
	@ cat .docker-token | docker login ghcr.io -u nachokruss --password-stdin

docker-build: ## Build multi-arch image (amd64 + arm64) and push to GHCR (tagged $(VERSION) and latest)
	docker buildx build --platform linux/amd64,linux/arm64 \
		-t $(GHCR_REPO):$(VERSION) \
		-t $(GHCR_REPO):latest \
		--push .

docker-push: docker-login docker-build ## Login, build multi-arch image, and push to GHCR

docker-deploy: docker-push ## Alias for docker-push (build and deploy to GHCR)

up: ## Start local dev environment (local DB + remote qBittorrent)
	docker-compose up -d --build

down: ## Stop local dev environment
	docker-compose down

logs: ## View local dev logs
	docker-compose logs -f qbittorrent-stats

clean: ## Remove build artifacts and cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov/

# Database dump/load targets
# Requires pg_dump and psql in PATH (install postgresql-client if needed)
# Set TRUENAS_POSTGRES_* variables in your .env file

db-dump: ## Dump the TrueNAS PostgreSQL database to dump.sql
	@ [ -f .env ] && export $$(grep -v '^#' .env | xargs) || { echo "Error: .env file not found"; exit 1; }
	@echo "Dumping database from TrueNAS ($(TRUENAS_POSTGRES_HOST):$(TRUENAS_POSTGRES_PORT))..."
	PGPASSWORD="$$TRUENAS_POSTGRES_PASSWORD" pg_dump \
		-h "$$TRUENAS_POSTGRES_HOST" \
		-p "$$TRUENAS_POSTGRES_PORT" \
		-U "$$TRUENAS_POSTGRES_USER" \
		d "$$TRUENAS_POSTGRES_DB" \
		--no-owner --no-acl --clean --if-exists \
		> dump.sql
	@echo "Dump saved to dump.sql ($$(wc -l < dump.sql) lines)"

db-load: ## Load dump.sql into the local PostgreSQL container
	@ [ -f dump.sql ] || { echo "Error: dump.sql not found. Run 'make db-dump' first."; exit 1; }
	@ [ -f .env ] && export $$(grep -v '^#' .env | xargs) || { echo "Error: .env file not found"; exit 1; }
	@echo "Loading dump into local database (qbittorrent-stats-db)..."
	PGPASSWORD="$$POSTGRES_PASSWORD" psql \
		-h "localhost" \
		-p "5432" \
		-U "$$POSTGRES_USER" \
		d "$$POSTGRES_DB" \
		< dump.sql
	@echo "Database loaded successfully."

db-dump-load: db-dump db-load ## Dump from TrueNAS and load into local database in one step

db-clean: ## Reset the local PostgreSQL database (drops and recreates the volume)
	@echo "Stopping local services..."
	docker-compose down
	@echo "Removing PostgreSQL volume..."
	docker volume rm -f qbittorrent-stats_postgres_data
	@echo "Database volume removed. Run 'make up' to start fresh."

