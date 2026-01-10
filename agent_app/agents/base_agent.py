from typing import Optional
from google.adk.models import BaseLlm

class BaseSpecialistAgent:
    """
    Base class for specialist agents that wraps an LLM with a specific instruction.
    This avoids the need for ADK's complex Runner infrastructure.
    """
    def __init__(self, model_client: BaseLlm, name: str, instruction: str):
        self.model_client = model_client
        self.name = name
        self.instruction = instruction
        self.tools = []
        
    def add_tool(self, tool):
        """Registers a tool with this agent."""
        self.tools.append(tool)
        
    async def run(self, context: str) -> "AgentResponse":
        """
        Runs the agent with the given context.
        Returns an AgentResponse with a text attribute.
        """
        # Build the prompt with instruction + context
        # Include tool descriptions if available
        tool_descriptions = ""
        if self.tools:
            tool_names = [getattr(t, '__name__', str(t)) for t in self.tools[:10]]  # Limit to first 10
            tool_descriptions = f"\n\nAvailable tools: {', '.join(tool_names)}"
        
        prompt = f"""
{self.instruction}
{tool_descriptions}

# Current Task
{context}

Please complete this task using the available information and tools.
"""
        
        response = await self.model_client.generate(prompt)
        return response


class AgentResponse:
    """Simple response wrapper"""
    def __init__(self, text: str):
        self.text = text
