from google.adk import Agent
from google.adk.models import BaseLlm

class ReportWriterAgent(Agent):
    """
    Formats long-form artifacts (status reports) from structured signals.
    This agent does NOT retrieve data - it only uses the Evidence Store.
    """
    def __init__(self, model_client: BaseLlm):
        super().__init__(
            model=model_client,
            name="ReportWriterAgent",
            instruction=(
                "You are the Report Writer Agent. Your role is to compose structured reports.\n"
                "You will receive evidence from the Evidence Store containing:\n"
                "- Email summaries and action items\n"
                "- Calendar events and meeting notes\n"
                "- Drive file information and blockers\n\n"
                "Your output should be a well-formatted report with the following sections:\n"
                "1. Summary\n"
                "2. Accomplishments\n"
                "3. Plan/Next Steps\n"
                "4. Blockers/Risks\n"
                "5. Asks/Decisions Needed\n"
                "6. References (links to source items)\n\n"
                "DO NOT retrieve new data. Only use the evidence provided to you."
            )
        )
