from google.adk.models import BaseLlm
from .base_agent import BaseSpecialistAgent

class MailAnalystAgent(BaseSpecialistAgent):
    def __init__(self, model_client: BaseLlm):
        super().__init__(
            model_client=model_client,
            name="MailAnalystAgent",
            instruction=(
                "You are the Mail Analyst Agent. Your role is to interact with Microsoft Mail/Outlook.\n"
                "You have access to tools for searching messages, reading bodies, and managing folders.\n"
                "When given a task, prefer using available tools to fetch real data.\n"
                "Summarize your findings clearly."
            )
        )
