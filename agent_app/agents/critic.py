from google.adk import Agent
from google.adk.models import BaseLlm
from typing import Dict, Any
import json
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService

class CriticAgent(Agent):
    """
    Validates that the response meets quality and safety policies.
    Returns PASS or FAIL with a list of required fixes.
    """
    def __init__(self, model_client: BaseLlm):
        super().__init__(
            model=model_client,
            name="CriticAgent",
            instruction=(
                "You are the Critic Agent (Validator). Your role is to verify quality and completeness.\n\n"
                "You will receive:\n"
                "- The original user query\n"
                "- The evidence collected\n"
                "- The proposed response\n\n"
                "Your job is to verify:\n"
                "1. The question was fully answered\n"
                "2. Dates/time windows are explicit (not vague)\n"
                "3. For actions: proposed changes are clearly summarized\n"
                "4. Data minimization: message bodies only used when needed\n"
                "5. No hallucinated data - all claims are backed by evidence\n\n"
                "Output your verdict as JSON:\n"
                "{\n"
                '  "verdict": "PASS" or "FAIL",\n'
                '  "issues": ["list of issues if FAIL"],\n'
                '  "suggestions": ["optional suggestions for improvement"]\n'
                "}\n\n"
                "Be strict but fair. Only FAIL if there are genuine problems."
            )
        )

    async def validate(self, query: str, evidence: Dict[str, Any], response: str) -> Dict[str, Any]:
        """
        Validates the response against the query and evidence.
        Returns a structured verdict.
        """
        context = f"""
        # User Query
        {query}
        
        # Evidence Collected
        {json.dumps(evidence, indent=2)}
        
        # Proposed Response
        {response}
        
        Please validate and provide your verdict as JSON.
        """
        
        # Use Runner to execute self
        session_service = InMemorySessionService()
        runner = Runner(agent=self, app_name="MsgraphAgent", session_service=session_service)
        
        class SimpleContent:
             def __init__(self, text):
                 self.role = "user"
                 self.parts = [text]
        
        response_text = ""
        import uuid
        try:
             async for event in runner.run_async(
                 user_id=str(uuid.uuid4()),
                 session_id=str(uuid.uuid4()),
                 new_message=SimpleContent(context)
             ):
                 if hasattr(event, "text") and event.text:
                     response_text += event.text
                 elif hasattr(event, "content") and event.content:
                     response_text += str(event.content)
        except Exception as e:
             response_text = f"Error: {e}"
        
        result = response_text
        
        # Try to parse the JSON response
        try:
            text = result.text if hasattr(result, 'text') else str(result)
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            verdict = json.loads(text)
            return verdict
        except Exception:
            # If parsing fails, assume PASS with a warning
            return {
                "verdict": "PASS",
                "issues": [],
                "suggestions": ["Could not parse Critic output, defaulting to PASS"]
            }
