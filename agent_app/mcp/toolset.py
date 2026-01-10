import asyncio
import os
import logging
from typing import List, Callable, Dict, Any, Optional
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.types import Tool
from contextlib import AsyncExitStack

logger = logging.getLogger(__name__)

class McpToolset:
    def __init__(self, server_url: str, auth_token: Optional[str] = None):
        self.server_url = server_url
        self.auth_token = auth_token
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.session_id: Optional[str] = None

    def set_session_id(self, session_id: str):
        """
        Sets the session ID to be injected into future tool calls.
        """
        self.session_id = session_id

    async def initialize(self):
        """
        Connects to the Remote MCP Server via SSE.
        """
        # Connect via SSE with headers if token is present
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        
        logger.debug(f"Connecting to MCP server: {self.server_url}")
        self.sse_context = sse_client(self.server_url, headers=headers)
        self.read, self.write = await self.exit_stack.enter_async_context(self.sse_context)
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.read, self.write))
        await self.session.initialize()
        logger.info("MCP Session initialized.")

    async def list_tools(self) -> List[Tool]:
        if not self.session:
            return []
        result = await self.session.list_tools()
        logger.debug(f"Listed {len(result.tools)} tools from MCP.")
        return result.tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        if not self.session:
            raise RuntimeError("MCP Session not initialized")
        logger.debug(f"Calling tool: {name} with arguments: {arguments}")
        result = await self.session.call_tool(name, arguments)
        return result

    async def get_adk_tools(self) -> List[Callable]:
        """
        Returns a list of callables that ADK agents can use.
        Dynamically creates functions based on available MCP tools.
        """
        if not self.session:
            return []
            
        mcp_tools = await self.list_tools()
        adk_tools = []
        
        for tool in mcp_tools:
            # Create a wrapper function that calls the MCP tool
            # We must capture 'tool.name' in the closure
            
            async def tool_wrapper(arguments: Dict[str, Any], _name=tool.name) -> str:
                """
                Dynamic wrapper for MCP tool.
                """
                try:
                    # Create a copy to avoid modifying the original dict
                    args = dict(arguments)
                    
                    # Strategy B: Automatic Session Injection
                    # If we have a session_id, inject it into the arguments
                    if self.session_id:
                        if "session_id" not in args:
                             args["session_id"] = self.session_id
                             
                    result = await self.call_tool(_name, args)
                    # Result is typically an object with 'content'. 
                    # We assume text content for the Agent.
                    if hasattr(result, 'content') and result.content:
                        # Join all text content
                        return "\n".join([c.text for c in result.content if c.type == 'text'])
                    return str(result)
                except Exception as e:
                    return f"Error calling tool {_name}: {str(e)}"
            
            # Set metadata for the ADK agent (Model) to understand the tool
            # The ADK likely inspects __name__, __doc__, and type hints.
            tool_wrapper.__name__ = tool.name
            tool_wrapper.__doc__ = tool.description or f"Call MCP tool {tool.name}"
            # Note: Robust argument typing is hard dynamically. 
            # We rely on the model emitting a dict for 'arguments'.
            
            adk_tools.append(tool_wrapper)
            
        return adk_tools

    async def close(self):
        await self.exit_stack.aclose()
