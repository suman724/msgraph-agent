from google.adk import Agent
from google.adk.models import BaseLlm

class CalendarAnalystAgent(Agent):
    def __init__(self, model_client: BaseLlm):
        super().__init__(
            model=model_client,
            instruction=(
                "You are the Calendar Analyst Agent. Your role is to interact with Microsoft Calendar.\n"
                "You have access to tools for listing events, finding availability, and scheduling meetings.\n"
                "Always check for conflicts before proposing new times.\n"
                "Use the provided tools to query the calendar."
            ),
            name="CalendarAnalystAgent"
        )
