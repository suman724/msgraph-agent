"""
Tests for WorkspaceCoordinatorAgent.

These tests verify the coordinator's orchestration logic by mocking the ADK Runner
and underlying model client.
"""
import pytest
import asyncio
from typing import Any
from unittest.mock import MagicMock, AsyncMock
import unittest.mock

from agent_app.agents.coordinator import WorkspaceCoordinatorAgent
from agent_app.config import Config
from agent_app.mcp.toolset import McpToolset
from agent_app.schemas.task_spec import TaskSpec, Step


@pytest.mark.asyncio
async def test_coordinator_pipeline_execution():
    """
    Test that the coordinator executes via the ADK pipeline (main_pipeline).
    
    Since the new architecture uses ParallelAgent, LoopAgent, etc., we mock
    the Runner to return a successful response, verifying the pipeline is invoked.
    """
    from google.adk.models import BaseLlm
    
    # 1. Mock Model Client
    mock_model_client = MagicMock(spec=BaseLlm)
    mock_response = MagicMock()
    mock_response.text = "Here is a summary of your emails from yesterday..."
    mock_model_client.generate = AsyncMock(return_value=mock_response)

    # 2. Mock MCP Toolset
    mock_mcp = MagicMock(spec=McpToolset)
    
    # 3. Initialize Coordinator
    coordinator = WorkspaceCoordinatorAgent(mock_model_client, mock_mcp)
    
    # 4. Patch Runner to simulate successful pipeline execution
    with unittest.mock.patch('agent_app.agents.coordinator.Runner') as MockRunner:
        mock_runner_instance = MockRunner.return_value
        
        # Async generator mock for run_async that yields a response
        async def async_gen(*args, **kwargs):
            mock_event = MagicMock()
            mock_event.text = "Summary: You received 5 emails yesterday about Project Alpha."
            yield mock_event
            
        mock_runner_instance.run_async = async_gen
        
        # Run the coordinator
        result = await coordinator.run("Summarize emails from yesterday")
        
        # 5. Assertions
        # Verify Runner was called (pipeline execution)
        assert MockRunner.call_count >= 1, "Runner should be called for pipeline execution"
        
        # Verify we got a response
        assert "Summary" in result or "email" in result.lower(), "Response should contain summary"


@pytest.mark.asyncio
async def test_coordinator_legacy_fallback():
    """
    Test that the coordinator falls back to legacy execution when pipeline fails.
    
    The legacy path populates evidence_store and uses _plan(), _execute_steps_parallel(), etc.
    """
    from google.adk.models import BaseLlm
    
    # 1. Mock Model Client
    mock_model_client = MagicMock(spec=BaseLlm)
    mock_response = MagicMock()
    mock_response.text = '{"intent": "summarize_emails", "steps": [{"step_id": "S1", "name": "Fetch Emails", "assigned_agent": "MailAnalystAgent", "inputs": {}}]}'
    mock_model_client.generate = AsyncMock(return_value=mock_response)

    # 2. Mock MCP Toolset
    mock_mcp = MagicMock(spec=McpToolset)
    
    # 3. Initialize Coordinator
    coordinator = WorkspaceCoordinatorAgent(mock_model_client, mock_mcp)
    
    # 4. Patch Runner to fail (triggers legacy fallback)
    with unittest.mock.patch('agent_app.agents.coordinator.Runner') as MockRunner:
        mock_runner_instance = MockRunner.return_value
        
        # Make pipeline return empty (triggers fallback)
        async def empty_gen(*args, **kwargs):
            if False:
                yield  # Empty generator
            
        mock_runner_instance.run_async = empty_gen
        
        # Run the coordinator (should fall back to legacy)
        result = await coordinator.run("Summarize emails from yesterday")
        
        # 5. Assertions
        # Verify legacy execution populated evidence store
        assert len(coordinator.evidence_store) > 0, "Evidence store should be populated by legacy fallback"
        assert "S1" in coordinator.evidence_store, "Step S1 should be in evidence store"
        
        # Verify model was called for planning
        assert mock_model_client.generate.call_count >= 1, "Model should be called for planning"
