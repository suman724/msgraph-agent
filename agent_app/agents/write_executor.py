import logging
from typing import Dict, Any, Optional
from ..mcp.toolset import McpToolset

logger = logging.getLogger(__name__)

class WriteExecutor:
    """
    A deterministic helper for executing write operations.
    Receives an approved action plan and executes the specific MCP write tools.
    This is NOT an LLM agent - it's a simple function invoker.
    """
    def __init__(self, mcp_toolset: McpToolset):
        self.mcp_toolset = mcp_toolset

    async def execute(self, action_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a write action.
        
        Args:
            action_type: Type of action (e.g., 'send_email', 'create_event', 'upload_file')
            payload: The structured payload for the action
            
        Returns:
            Result of the operation
        """
        logger.info(f"WriteExecutor executing: {action_type}")
        
        # Map action types to MCP tool names
        tool_mapping = {
            "send_email": "send_mail",
            "create_event": "create_calendar_event",
            "upload_file": "upload_file",
            "update_event": "update_calendar_event",
        }
        
        tool_name = tool_mapping.get(action_type)
        if not tool_name:
            return {"error": f"Unknown action type: {action_type}"}
        
        try:
            result = await self.mcp_toolset.call_tool(tool_name, payload)
            
            # Parse result
            if hasattr(result, 'content') and result.content:
                output = "\n".join([c.text for c in result.content if c.type == 'text'])
            else:
                output = str(result)
                
            return {
                "status": "success",
                "action": action_type,
                "output": output
            }
        except Exception as e:
            logger.error(f"WriteExecutor failed: {e}")
            return {
                "status": "error",
                "action": action_type,
                "error": str(e)
            }
