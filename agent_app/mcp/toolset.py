"""
MCP Toolset wrapper for MSGraph Agent.

This module provides a hybrid approach:
- Uses ADK's native McpToolset for agent tool consumption via StreamableHTTP
- Uses MCP SDK directly for PKCE authentication (call_tool) via StreamableHTTP

The wrapper handles:
- StreamableHTTP connection to the MCP server
- Session ID injection for authenticated requests
- Dynamic tool discovery and wrapping
"""

import logging
from typing import List, Callable, Dict, Any, Optional
from contextlib import AsyncExitStack

# MCP SDK imports for direct tool calls (PKCE auth)
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

# ADK imports for agent-compatible tools
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset as AdkMcpToolset
from google.adk.tools.mcp_tool.mcp_toolset import StreamableHTTPConnectionParams

logger = logging.getLogger(__name__)


class McpToolset:
    """
    Hybrid MCP Toolset combining ADK's McpToolset with direct MCP SDK access.
    
    This class provides:
    1. Direct tool calls via MCP SDK (for PKCE authentication flow)
    2. ADK-compatible tools via ADK's McpToolset (for agent consumption)
    
    Attributes:
        server_url: The URL of the MCP server
        auth_token: Optional Bearer token for authentication
        session_id: Optional session ID for MS Graph operations
    """
    
    def __init__(self, server_url: str, auth_token: Optional[str] = None):
        """
        Initialize the MCP Toolset.
        
        Args:
            server_url: The URL of the MCP server (e.g., http://localhost:8000/)
            auth_token: Optional Bearer token for initial authentication
        """
        self.server_url = server_url
        self.auth_token = auth_token
        self.session_id: Optional[str] = None
        
        # MCP SDK session for direct tool calls
        self._mcp_session: Optional[ClientSession] = None
        self._exit_stack = AsyncExitStack()
        
        # ADK toolset for agent-compatible tools
        self._adk_toolset: Optional[AdkMcpToolset] = None

    def set_session_id(self, session_id: str):
        """
        Sets the session ID to be injected into future tool calls.
        
        Args:
            session_id: The MS Graph session ID from PKCE authentication
        """
        self.session_id = session_id
        logger.info(f"Session ID set: {session_id[:8]}...")

    def _get_headers(self, context=None) -> Dict[str, str]:
        """
        Header provider for both MCP SDK and ADK's McpToolset.
        
        This injects auth token and session ID into requests.
        """
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        if self.session_id:
            headers["X-Session-Id"] = self.session_id
        return headers

    async def initialize(self):
        """
        Connects to the Remote MCP Server via StreamableHTTP.
        
        Initializes both:
        1. MCP SDK ClientSession for direct tool calls (PKCE)
        2. ADK's McpToolset for agent-compatible tools
        """
        logger.info(f"Connecting to MCP server: {self.server_url}")
        
        headers = self._get_headers()
        
        # -----------------------------------------------------------------
        # 1. Initialize MCP SDK session for direct tool calls (StreamableHTTP)
        # -----------------------------------------------------------------
        try:
            http_context = streamable_http_client(self.server_url, headers=headers)
            read, write = await self._exit_stack.enter_async_context(http_context)
            self._mcp_session = await self._exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await self._mcp_session.initialize()
            logger.info("MCP SDK session (StreamableHTTP) initialized for direct tool calls.")
        except Exception as e:
            logger.warning(f"Failed to initialize MCP SDK session: {e}")
        
        # -----------------------------------------------------------------
        # 2. Initialize ADK's McpToolset for agent tools (StreamableHTTP)
        # -----------------------------------------------------------------
        try:
            connection_params = StreamableHTTPConnectionParams(
                url=self.server_url,
                headers=headers
            )
            
            self._adk_toolset = AdkMcpToolset(
                connection_params=connection_params,
                header_provider=lambda ctx: self._get_headers(ctx)
            )
            logger.info("ADK McpToolset (StreamableHTTP) initialized for agent tools.")
        except Exception as e:
            logger.warning(f"Failed to initialize ADK McpToolset: {e}")

    async def list_tools(self) -> List[Any]:
        """
        Lists all available tools from the MCP server.
        """
        if self._mcp_session:
            result = await self._mcp_session.list_tools()
            logger.debug(f"Listed {len(result.tools)} tools from MCP.")
            return result.tools
        elif self._adk_toolset:
            tools = await self._adk_toolset.get_tools()
            return tools
        return []

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """
        Calls a tool on the MCP server directly.
        """
        if not self._mcp_session:
            raise RuntimeError("MCP SDK session not initialized. Cannot make direct tool calls.")
        
        if self.session_id and "session_id" not in arguments:
            arguments = dict(arguments)
            arguments["session_id"] = self.session_id
        
        logger.debug(f"Calling tool: {name} with arguments: {arguments}")
        result = await self._mcp_session.call_tool(name, arguments)
        return result

    async def get_adk_tools(self) -> List[Callable]:
        """
        Returns native ADK BaseTool objects.
        """
        if not self._adk_toolset:
            return []
            
        return await self._adk_toolset.get_tools()

    async def close(self):
        """
        Closes the MCP connections and cleans up resources.
        """
        await self._exit_stack.aclose()
        logger.info("MCP SDK session closed.")
        
        if self._adk_toolset:
            await self._adk_toolset.close()
            logger.info("ADK McpToolset closed.")
