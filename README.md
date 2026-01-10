# MSGraph Agent (Google ADK)

This agent uses the **Google Agent Development Kit (ADK)** to interact with Microsoft 365 services (Email, Calendar, OneDrive) via an MCP (Model Context Protocol) Server.

## Architecture

The agent follows a **Dispatcher + Specialist** topology with validation:

### Core Agents
- **WorkspaceCoordinatorAgent**: Plans tasks, delegates to specialists, manages course correction, and aggregates results.
- **Domain Specialists**: `MailAnalystAgent`, `CalendarAnalystAgent`, `DriveAnalystAgent` for domain-specific operations.
- **ReportWriterAgent**: Composes structured reports from evidence.
- **CriticAgent**: Validates responses for quality and completeness (PASS/FAIL).

### Infrastructure
- **MCP Toolset**: Connects to Remote MS Graph MCP Server via SSE with dynamic tool discovery.
- **McpAuthManager**: Handles interactive PKCE authentication flow.
- **WriteExecutor**: Non-LLM helper for write operations (after approval).

### Key Features
- **Parallel Fan-Out**: Independent steps execute concurrently.
- **Course Correction**: Automatic retry with expanded time windows or broadened queries.
- **Local Tools**: `parse_time_window`, `resolve_person`, `extract_action_items`.

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
# MCP_AUTH_TOKEN is optional if using PKCE, but can be used for initial connection if needed.
# export MCP_AUTH_TOKEN="your-secure-token" 
make run
```

### Authentication Flow (Interactive)

When the agent starts, it will initiate an interactive **PKCE Authentication** flow with Microsoft Graph:
1.  The agent will print a **Device Login URL** and a **Code**.
2.  Open the URL in your browser and enter the Code.
3.  Copy the resulting **Authorization Code** (or follow prompt instructions) and paste it back into the Agent's terminal.
4.  The agent will obtain a session ID and proceed.

## Testing

Run the test suite:

```bash
make test
```

## Development

- **Build**: Uses `setuptools` (not yet configured for packaging, just run from source).
- **CI**: GitHub Actions workflow in `.github/workflows/build.yml`.
