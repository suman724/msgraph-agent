from google.adk import Agent
from google.adk.models import BaseLlm

class DriveAnalystAgent(Agent):
    def __init__(self, model_client: BaseLlm):
        super().__init__(
            model=model_client,
            name="DriveAnalystAgent",
            instruction=(
                "You are the Drive Analyst Agent. Your role is to interact with Microsoft OneDrive.\n"
                "You have access to tools for listing items, searching for files, and reading content.\n"
                "Use specific search queries to find relevant documents.\n"
                "Report tool outputs accurately."
            )
        )
