from google.adk.models import BaseLlm
from .base_agent import BaseSpecialistAgent

class CalendarAnalystAgent(BaseSpecialistAgent):
    def __init__(self, model_client: BaseLlm):
        super().__init__(
            model_client=model_client,
            name="CalendarAnalystAgent",
            instruction=(
                "You are the Calendar Analyst Agent. Your role is to interact with Microsoft Calendar.\n"
                "You have access to tools for listing events, finding availability, and scheduling meetings.\n"
                "Always check for conflicts before proposing new times.\n"
                "Use the provided tools to query the calendar."
            )
        )
