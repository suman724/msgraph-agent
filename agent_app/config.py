import os
import logging
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

@dataclass
class Config:
    # MCP Server Configuration (Remote)
    # The URL of the MCP Server (e.g., http://localhost:8000/sse)
    mcp_server_url: str = os.getenv("MCP_SERVER_URL", "http://localhost:8000/sse")
    # Authorization Token for MCP Server
    mcp_auth_token: Optional[str] = os.getenv("MCP_AUTH_TOKEN")
    
    # Model Configuration (Azure/OpenAI)
    model_name: str = os.getenv("MODEL_NAME", "gpt-5")
    model_base_url: Optional[str] = os.getenv("MODEL_BASE_URL")
    
    # Validation
    def validate(self):
        if not self.mcp_server_url:
            logger.warning("MCP_SERVER_URL is not set. The agent will not be able to connect to the MCP server.")
        if not self.mcp_auth_token:
            logger.warning("MCP_AUTH_TOKEN is not set. Connection might fail if server requires authentication.")
        if not self.model_name:
            logger.warning("MODEL_NAME is not set.")

config = Config()
