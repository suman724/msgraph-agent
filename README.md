# MSGraph Agent (Google ADK)

This agent uses the **Google Agent Development Kit (ADK)** to interact with Microsoft 365 services (Email, Calendar, OneDrive) via an MCP (Model Context Protocol) Server.

## Architecture

The agent follows a **Dispatcher + Specialist** topology:
- **WorkspaceCoordinatorAgent**: Plans tasks and delegates to specialists.
- **Specialists**: `MailAnalystAgent`, `CalendarAnalystAgent`, `DriveAnalystAgent`.
- **MCP Toolset**: Connects to a Remote MS Graph MCP Server via SSE (Server-Sent Events) and dynamically discovers available tools.

## Prerequisites

- Python 3.12+
- An MCP Server executable (e.g., the Microsoft Graph MCP server).
- Credentials for MS Graph (handled by the MCP server).

## Setup

1. **Create and Activate Virtual Environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. **Install Dependencies**:
   ```bash
   # Install via Makefile (installs in editable mode with dev dependencies)
   make install
   
   # OR manual install
   pip install -e ".[dev]"
   ```

## Configuration

The agent **requires** the MCP server to be configured via Environment Variables (or `.env` file).

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_URL` | **Required** | The URL of the Remote MCP Server (e.g., `http://localhost:8000/sse`). |
| `MCP_AUTH_TOKEN` | None | Authorization token for the MCP Server (sent as Bearer token). |
| `MODEL_NAME` | `gpt-5` | The name of the model to use (e.g., `gpt-5`, `azure/gpt-4o`). |
| `MODEL_BASE_URL` | None | Base URL for the LLM API (e.g., Azure OpenAI endpoint). |

## Running the Agent

Start the agent in CLI mode. Ensure you have set `MCP_SERVER_URL`.

```bash
export MCP_SERVER_URL="http://localhost:8000/sse"
export MCP_AUTH_TOKEN="your-secure-token"
make run
```

## Testing

Run the test suite:

```bash
make test
```

## Development

- **Build**: Uses `setuptools` (not yet configured for packaging, just run from source).
- **CI**: GitHub Actions workflow in `.github/workflows/build.yml`.
