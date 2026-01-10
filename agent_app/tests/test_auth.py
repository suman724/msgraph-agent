import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from agent_app.mcp.auth import McpAuthManager
from agent_app.mcp.toolset import McpToolset
from mcp.types import Tool, TextContent

@pytest.mark.asyncio
async def test_auth_manager_flow():
    # 1. Mock Toolset
    mock_toolset = MagicMock(spec=McpToolset)
    
    # Mock begin_pkce response
    mock_begin_c = MagicMock(spec=TextContent)
    mock_begin_c.type = 'text'
    mock_begin_c.text = "Please visit https://microsoft.com/devicelogin"
    mock_begin_res = MagicMock()
    mock_begin_res.content = [mock_begin_c]
    
    # Mock complete_pkce response
    mock_complete_c = MagicMock(spec=TextContent)
    mock_complete_c.type = 'text'
    mock_complete_c.text = "session_12345"
    mock_complete_res = MagicMock()
    mock_complete_res.content = [mock_complete_c]

    # Setup async return values
    mock_toolset.call_tool = AsyncMock(side_effect=[mock_begin_res, mock_complete_res])

    # 2. Init Manager
    manager = McpAuthManager(mock_toolset)

    # 3. Patch input to simulate user pasting code
    with patch('builtins.input', return_value="ABC-123"):
        session_id = await manager.authenticate()

    # 4. Assertions
    assert session_id == "session_12345"
    
    # Verify calls
    # First call: begin_pkce
    mock_toolset.call_tool.assert_any_call("begin_pkce", {})
    # Second call: complete_pkce with code
    mock_toolset.call_tool.assert_any_call("complete_pkce", {"code": "ABC-123"})
