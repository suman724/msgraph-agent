import pytest
import asyncio
from typing import Any
from unittest.mock import MagicMock, AsyncMock

from agent_app.agents.coordinator import WorkspaceCoordinatorAgent
from agent_app.config import Config
from agent_app.mcp.toolset import McpToolset
from agent_app.schemas.task_spec import TaskSpec, Step

@pytest.mark.asyncio
async def test_coordinator_plan_execution():
    # 1. Mock Model Client
    # We can mock BaseLlm. It's an abstract class so we just mock the generate method on a dummy object
    # or use MagicMock(spec=BaseLlm) if we import it.
    from google.adk.models import BaseLlm
    mock_model_client = MagicMock(spec=BaseLlm)
    
    mock_response = MagicMock()
    # Return a JSON plan for "Summarize emails"
    mock_response.text = '{"intent": "summarize_emails", "steps": [{"step_id": "S1", "name": "Fetch Emails", "assigned_agent": "MailAnalystAgent", "inputs": {}}]}'
    mock_model_client.generate = AsyncMock(return_value=mock_response)

    # 2. Mock MCP Toolset
    mock_mcp = MagicMock(spec=McpToolset)
    
    # 3. Initialize Coordinator
    coordinator = WorkspaceCoordinatorAgent(mock_model_client, mock_mcp)
    
    # 4. Mock Specialist Execution (since we don't haven't wired up the specialists to real model yet)
    # We can mock the specialists dict if needed, or rely on the mock model client to drive them if they used it.
    # But currently Specialists use the SAME model client.
    
    # Run
    result = await coordinator.run("Summarize emails from yesterday")
    
    # 5. Assertions
    # Verify plan was generated
    assert len(coordinator.evidence_store) > 0, "Evidence store should not be empty"
    assert "S1" in coordinator.evidence_store
    
    # Verify Model called (once for plan, once for synthesis - or more if specialists called it)
    assert mock_model_client.generate.call_count >= 2
