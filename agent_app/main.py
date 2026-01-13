"""
MSGraph Agent - Main Entry Point

This module initializes and runs the MSGraph Agent using Google ADK.

Architecture:
    1. Initialize ADK's McpToolset for MS Graph operations
    2. Authenticate via PKCE with McpAuthManager
    3. Initialize model client (Gemini or LiteLLM)
    4. Create and run the WorkspaceCoordinatorAgent
"""

import asyncio
import os
import logging

from agent_app.config import config
from agent_app.mcp.toolset import McpToolset
from agent_app.agents.coordinator import WorkspaceCoordinatorAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("agent.log")
    ]
)
logger = logging.getLogger(__name__)


def get_model_client():
    """
    Creates the appropriate model client based on configuration.
    
    Supports:
    - Gemini models (default, native ADK support)
    - OpenAI/Azure models via LiteLLM (requires litellm package)
    
    Returns:
        A BaseLlm-compatible model client
    """
    model_name = config.model_name
    
    # Check if using Gemini models (native ADK support)
    if model_name.startswith("gemini"):
        try:
            from google.adk.models import Gemini
            logger.info(f"Using Gemini model: {model_name}")
            return Gemini(model=model_name)
        except Exception as e:
            logger.warning(f"Failed to initialize Gemini: {e}")
    
    # Try LiteLLM for OpenAI/Azure models
    try:
        from google.adk.models.lite_llm import LiteLlm
        logger.info(f"Using LiteLLM model: {model_name}")
        return LiteLlm(model=model_name)
    except ImportError:
        logger.warning("LiteLLM not installed. Install with: pip install litellm")
    except Exception as e:
        logger.warning(f"Failed to initialize LiteLLM: {e}")
    
    # Fallback to development client
    logger.warning("Using development model client")
    from google.adk.models import BaseLlm
    
    class DevelopmentModelClient(BaseLlm):
        """Development model client for testing when no real model is available."""
        
        async def generate(self, prompt: str, **kwargs):
            """Returns a fixed response for development."""
            class Response:
                text = '{"intent": "dev_response", "steps": []}'
            return Response()
    
    return DevelopmentModelClient()


async def main():
    """
    Main entry point for the MSGraph Agent.
    
    Orchestrates:
    1. MCP Toolset initialization
    2. PKCE Authentication
    3. Model client setup
    4. Agent initialization and CLI loop
    """
    logger.info("Starting MSGraph Agent...")
    
    mcp = None
    try:
        # --------------------------------------------------------
        # Step 1: Initialize MCP Toolset (using ADK's McpToolset)
        # --------------------------------------------------------
        logger.info(f"Initializing MCP Toolset with URL: {config.mcp_server_url}")
        mcp = McpToolset(
            server_url=config.mcp_server_url,
            auth_token=config.mcp_auth_token
        )
        await mcp.initialize()
        
        # --------------------------------------------------------
        # Step 2: PKCE Authentication with Microsoft Graph
        # --------------------------------------------------------
        from agent_app.mcp.auth import McpAuthManager
        auth_manager = McpAuthManager(mcp)
        session_id = await auth_manager.authenticate()
        
        if session_id:
            logger.info(f"Setting Session ID: {session_id[:8]}...")
            mcp.set_session_id(session_id)
        else:
            logger.warning("No session ID returned from Auth. Continuing without it (might fail).")
            
    except Exception as e:
        logger.critical(f"Failed to initialize/authenticate: {e}", exc_info=True)
        return
    
    try:
        # --------------------------------------------------------
        # Step 3: Initialize Model Client
        # --------------------------------------------------------
        model_client = get_model_client()
        logger.info(f"Model client initialized: {type(model_client).__name__}")

        # --------------------------------------------------------
        # Step 4: Create Coordinator Agent
        # --------------------------------------------------------
        coordinator = WorkspaceCoordinatorAgent(model_client, mcp)
        await coordinator.initialize()
        logger.info("Coordinator agent initialized")
        
        # --------------------------------------------------------
        # Step 5: CLI Loop
        # --------------------------------------------------------
        print("\n" + "="*60)
        print("MSGraph Agent Ready")
        print("="*60)
        print("Commands:")
        print("  - Type your query to interact with Mail, Calendar, Drive")
        print("  - Type 'exit' or 'quit' to stop")
        print("="*60 + "\n")
        
        while True:
            try:
                user_input = input("User: ").strip()
                
                if not user_input:
                    continue
                    
                if user_input.lower() in ["exit", "quit"]:
                    break
                
                logger.info(f"Processing user query: {user_input}")
                response = await coordinator.run(user_input)
                print(f"\nAgent: {response}\n")
                
            except KeyboardInterrupt:
                logger.info("User interrupted session.")
                break
            except Exception as e:
                logger.error(f"Error processing query: {e}", exc_info=True)
                print("An error occurred. Check agent.log for details.")

    except Exception as e:
        logger.critical(f"Unhandled exception in main loop: {e}", exc_info=True)
    finally:
        logger.info("Shutting down...")
        if mcp:
            await mcp.close()


if __name__ == "__main__":
    asyncio.run(main())
