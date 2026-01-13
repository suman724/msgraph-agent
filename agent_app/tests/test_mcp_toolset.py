"""
Tests for McpToolset - wrapper around ADK's native McpToolset using StreamableHTTP.

These tests verify the McpToolset wrapper correctly:
1. Initializes with ADK's McpToolset using StreamableHTTP
2. Handles session ID injection
3. Provides ADK-compatible tools
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.mark.asyncio
async def test_mcp_toolset_initialization():
    """
    Verifies that McpToolset initializes ADK's underlying McpToolset with StreamableHTTP.
    """
    # Mock streamable_http_client context manager
    mock_http_client = MagicMock()
    mock_http_context = AsyncMock()
    mock_read = MagicMock()
    mock_write = MagicMock()
    mock_http_client.return_value = mock_http_context
    mock_http_context.__aenter__.return_value = (mock_read, mock_write)

    # Mock ADK toolset
    with patch("agent_app.mcp.toolset.AdkMcpToolset") as MockAdkToolset:
        with patch("agent_app.mcp.toolset.StreamableHTTPConnectionParams") as MockHttpParams:
            with patch("agent_app.mcp.toolset.streamable_http_client", side_effect=mock_http_client):
                from agent_app.mcp.toolset import McpToolset
                
                server_url = "http://test-server/"
                auth_token = "secret-token"
                
                toolset = McpToolset(server_url=server_url, auth_token=auth_token)
                await toolset.initialize()
                
                # Verify StreamableHTTPConnectionParams was created with correct URL
                MockHttpParams.assert_called_once()
                call_kwargs = MockHttpParams.call_args
                assert call_kwargs.kwargs["url"] == server_url
                
                # Verify ADK McpToolset was instantiated
                MockAdkToolset.assert_called_once()


@pytest.mark.asyncio
async def test_mcp_toolset_session_id_injection():
    """
    Verifies that session ID is properly stored for injection.
    """
    from agent_app.mcp.toolset import McpToolset
    
    toolset = McpToolset("http://mock")
    
    # Initially no session ID
    assert toolset.session_id is None
    
    # Set session ID
    toolset.set_session_id("sess_abc123")
    
    # Verify it's stored
    assert toolset.session_id == "sess_abc123"
    
    # Verify headers include session ID
    headers = toolset._get_headers()
    assert "X-Session-Id" in headers
    assert headers["X-Session-Id"] == "sess_abc123"


@pytest.mark.asyncio
async def test_mcp_toolset_headers_with_auth():
    """
    Verifies that Authorization header is included when auth_token is provided.
    """
    from agent_app.mcp.toolset import McpToolset
    
    toolset = McpToolset("http://mock", auth_token="my-token")
    
    headers = toolset._get_headers()
    assert "Authorization" in headers
    assert headers["Authorization"] == "Bearer my-token"


@pytest.mark.asyncio
async def test_mcp_toolset_headers_without_auth():
    """
    Verifies that no Authorization header when auth_token is None.
    """
    from agent_app.mcp.toolset import McpToolset
    
    toolset = McpToolset("http://mock", auth_token=None)
    
    headers = toolset._get_headers()
    assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_mcp_toolset_get_adk_tools():
    """
    Verifies that get_adk_tools returns tools from ADK's toolset.
    """
    # Mock streamable_http_client context manager
    mock_http_context = AsyncMock()
    mock_read = MagicMock()
    mock_write = MagicMock()
    mock_http_context.__aenter__.return_value = (mock_read, mock_write)

    with patch("agent_app.mcp.toolset.AdkMcpToolset") as MockAdkToolset:
        with patch("agent_app.mcp.toolset.StreamableHTTPConnectionParams"):
            with patch("agent_app.mcp.toolset.streamable_http_client", return_value=mock_http_context):
                from agent_app.mcp.toolset import McpToolset
                
                # Setup mock tools
                mock_tool1 = MagicMock()
                mock_tool1.name = "tool1"
                mock_tool2 = MagicMock()
                mock_tool2.name = "tool2"
                
                mock_adk_instance = MagicMock()
                mock_adk_instance.get_tools = AsyncMock(return_value=[mock_tool1, mock_tool2])
                MockAdkToolset.return_value = mock_adk_instance
                
                toolset = McpToolset("http://mock")
                await toolset.initialize()
                
                tools = await toolset.get_adk_tools()
                
                assert len(tools) == 2
                assert tools[0].name == "tool1"
                assert tools[1].name == "tool2"
