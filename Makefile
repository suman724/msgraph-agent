# Load environment variables from .env file if it exists
-include .env
export

# Environment Variable defaults/placeholders
# Required: The URL of the Remote MCP Server
MCP_SERVER_URL ?= http://localhost:8000/sse
# Authorization Token for MCP Server (Optional)
MCP_AUTH_TOKEN ?= 
# The model name to use (e.g., gpt-5)
MODEL_NAME ?= gpt-5
# Model Base URL (Required for Azure/Custom endpoints)
MODEL_BASE_URL ?= 

.PHONY: install test lint run clean help

install:
	pip install -e ".[dev]"

test:
	PYTHONPATH=. pytest agent_app/tests/

lint:
	# Add linting commands here, e.g. ruff check .
	@echo "Linting..."

run:
	@echo "Starting Agent..."
	@echo "Configuration:"
	@echo "  MCP_SERVER_URL: $(MCP_SERVER_URL)"
	@echo "  MCP_AUTH_TOKEN: $(if $(MCP_AUTH_TOKEN),******,Not Set)"
	@echo "  MODEL_NAME:     $(MODEL_NAME)"
	@echo "  MODEL_BASE_URL: $(MODEL_BASE_URL)"
	@if [ -z "$(MCP_SERVER_URL)" ]; then \
		echo "ERROR: MCP_SERVER_URL is not set."; \
		exit 1; \
	fi
	python -m agent_app.main

clean:
	rm -rf __pycache__ .pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +

help:
	@echo "Available targets:"
	@echo "  install  - Install dependencies (editable mode)"
	@echo "  test     - Run tests"
	@echo "  run      - Run the agent (Requires MCP_COMMAND)"
	@echo "  clean    - Cleanup build artifacts"
