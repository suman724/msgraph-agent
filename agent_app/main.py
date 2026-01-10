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

async def main():
    logger.info("Starting MSGraph Agent...")
    
    try:
        # 1. Initialize MCP
        logger.info(f"Initializing MCP Toolset with URL: {config.mcp_server_url}")
        mcp = McpToolset(server_url=config.mcp_server_url, auth_token=config.mcp_auth_token)
        await mcp.initialize()
        
        # 1.5 PKCE Authentication
        from agent_app.mcp.auth import McpAuthManager
        auth_manager = McpAuthManager(mcp)
        session_id = await auth_manager.authenticate()
        
        if session_id:
            logger.info(f"Setting Session ID: {session_id}")
            mcp.set_session_id(session_id)
        else:
            logger.warning("No session ID returned from Auth. Continuing without it (might fail).")
            
    except Exception as e:
        logger.critical(f"Failed to initialize/authenticate: {e}", exc_info=True)
        return
    
    try:
        # 2. Initialize Model Functionality
        # This requires setting up the ADK model client.
        # Logic to pick model based on config
        # model_client = ...
        
        # MOCK Model Client for scaffolding run
        # In production this would use the appropriate ADK model client (e.g. OpenAIModel, VertexAIModel)
        # configured with config.model_name and config.model_base_url
        from google.adk.models import BaseLlm
        class MockModelClient(BaseLlm):
            async def generate(self, prompt: str, **kwargs):
                class Response:
                    text = '{"intent": "summarize_emails", "steps": [{"step_id": "S1", "name": "Fetch Emails", "assigned_agent": "MailAnalystAgent", "inputs": {}}]}'
                return Response()
                
        model_client = MockModelClient()

        # 3. Create Coordinator
        coordinator = WorkspaceCoordinatorAgent(model_client, mcp)
        await coordinator.initialize()
        
        # 4. Run Loop (CLI)
        print("Agent Ready. Type 'exit' to quit.")
        while True:
            try:
                user_input = input("User: ")
                if user_input.strip().lower() in ["exit", "quit"]:
                    break
                
                logger.info(f"Processing user query: {user_input}")
                response = await coordinator.run(user_input)
                print(f"Agent: {response}")
                
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
        await mcp.close()

if __name__ == "__main__":
    asyncio.run(main())
