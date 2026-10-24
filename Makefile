.PHONY: test lint build run clean help docker-login docker-build docker-push docker-deploy

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

run: ## Run the container (requires external networks)
	docker-compose up -d

stop: ## Stop the running container
	docker-compose down

clean: ## Remove build artifacts and cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov/
