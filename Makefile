.PHONY: test lint build run clean help

PYTHON := .venv/bin/python

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

build: ## Build the Docker image
	docker build -t qbittorrent-stats:latest .

run: ## Run the container (requires external networks)
	docker-compose up -d

stop: ## Stop the running container
	docker-compose down

clean: ## Remove build artifacts and cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov/
