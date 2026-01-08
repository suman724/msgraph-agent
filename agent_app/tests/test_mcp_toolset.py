import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from agent_app.mcp.toolset import McpToolset

@pytest.mark.asyncio
async def test_mcp_toolset_initialization_with_auth():
    """
    Verifies that McpToolset passes the Authorization header when auth_token is provided.
    """
    server_url = "http://test-server/sse"
    auth_token = "secret-token"
    
    # Mock sse_client context manager
    mock_sse_client = MagicMock()
    mock_sse_context = AsyncMock()
    mock_read = MagicMock()
    mock_write = MagicMock()
    
    # Setup async context manager return values
    mock_sse_client.return_value = mock_sse_context
    mock_sse_context.__aenter__.return_value = (mock_read, mock_write)
    mock_sse_context.__aexit__.return_value = None
    
    # Mock ClientSession
    with patch("agent_app.mcp.toolset.sse_client", side_effect=mock_sse_client) as patched_sse_client:
        with patch("agent_app.mcp.toolset.ClientSession") as MockClientSession:
            # Setup ClientSession mock
            mock_session = AsyncMock()
            MockClientSession.return_value = mock_session
            mock_session.__aenter__.return_value = mock_session
            
            toolset = McpToolset(server_url=server_url, auth_token=auth_token)
            await toolset.initialize()
            
            # Assert sse_client was called with headers
            patched_sse_client.assert_called_once_with(server_url, headers={"Authorization": f"Bearer {auth_token}"})
            
            # Assert session was initialized
            mock_session.initialize.assert_awaited_once()

@pytest.mark.asyncio
async def test_mcp_toolset_initialization_without_auth():
    """
    Verifies that McpToolset does NOT pass Authorization header when auth_token is None.
    """
    server_url = "http://test-server/sse"
    
    # Mock sse_client
    mock_sse_client = MagicMock()
    mock_sse_context = AsyncMock()
    mock_read = MagicMock()
    mock_write = MagicMock()
    
    mock_sse_client.return_value = mock_sse_context
    mock_sse_context.__aenter__.return_value = (mock_read, mock_write)
    
    with patch("agent_app.mcp.toolset.sse_client", side_effect=mock_sse_client) as patched_sse_client:
        with patch("agent_app.mcp.toolset.ClientSession") as MockClientSession:
            mock_session = AsyncMock()
            MockClientSession.return_value = mock_session
            mock_session.__aenter__.return_value = mock_session

            toolset = McpToolset(server_url=server_url, auth_token=None)
            await toolset.initialize()
            
            # Assert sse_client was called with empty headers or no headers (depending on implementation)
            # In my impl, I pass headers={} if no auth.
            patched_sse_client.assert_called_once_with(server_url, headers={})
            
            mock_session.initialize.assert_awaited_once()
