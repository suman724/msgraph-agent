import logging
from typing import Dict, Any, Optional
from .toolset import McpToolset

logger = logging.getLogger(__name__)

class McpAuthManager:
    """
    Manages the Interactive PKCE Authentication flow for Microsoft Graph.
    """
    def __init__(self, toolset: McpToolset):
        self.toolset = toolset

    async def authenticate(self) -> str:
        """
        Executes the interactive PKCE flow:
        1. Call 'begin_pkce' -> Get URL & Verifier
        2. Prompt User to visit URL
        3. Get Code from User
        4. Call 'complete_pkce' -> Get Session ID
        
        Returns:
            str: The obtained session_id.
        """
        logger.info("Starting PKCE Authentication Flow...")
        
        # 1. Begin PKCE
        # We assume the tool is named 'begin_pkce' and returns a string or JSON with the URL.
        # Based on typical patterns, it might return a list of content blocks.
        try:
            # Note: arguments might be empty or specific to the server implementation
            result = await self.toolset.call_tool("begin_pkce", {})
            
            # Parse the result to find the URL. 
            # We assume result.content is a list of TextContent
            # The exact format depends on the MCP server implementation.
            # We'll treat the whole text as the instructions including URL if not structured.
            auth_info = ""
            if hasattr(result, 'content') and result.content:
                 auth_info = "\n".join([c.text for c in result.content if c.type == 'text'])
            else:
                auth_info = str(result)
                
            print("\n" + "="*60)
            print("AUTHENTICATION REQUIRED")
            print("="*60)
            print("The Agent needs to authenticate with Microsoft Graph.")
            print(f"\nPlease follow these instructions:\n{auth_info}")
            print("-" * 60)
            
            # 2. & 3. Interaction
            code = input("\nENTER the Authorization Code (or result) from the browser page: ").strip()
            
            if not code:
                raise ValueError("Authentication code cannot be empty.")
                
            # 4. Complete PKCE
            # We assume the tool 'complete_pkce' takes 'code' as an argument.
            # It might also need 'code_verifier' if the server returned it in step 1, 
            # but usually 'begin_pkce' caches it server-side or returns it.
            # If the server is stateless, begin_pkce returns verifier, and we must pass it back.
            # For this implementation, we assume the user just pastes the 'code'.
            
            logger.info("Completing PKCE flow...")
            session_result = await self.toolset.call_tool("complete_pkce", {"code": code})
            
            # Extract Session ID
            # Again, assuming text content contains the ID or is the ID.
            session_id = ""
            if hasattr(session_result, 'content') and session_result.content:
                 session_id = "".join([c.text for c in session_result.content if c.type == 'text']).strip()
            else:
                 session_id = str(session_result).strip()
                 
            logger.info("Authentication successful. Session ID obtained.")
            return session_id
            
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise RuntimeError(f"Failed to authenticate: {e}")
