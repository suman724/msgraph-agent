import json
from google.adk.models import BaseLlm
import logging
from typing import Dict, Any, List, Optional
from google.adk import Agent
from ..schemas.task_spec import TaskSpec, Step
from .mail_agent import MailAnalystAgent
from .calendar_agent import CalendarAnalystAgent
from .drive_agent import DriveAnalystAgent
from ..mcp.toolset import McpToolset

# Setup logging
logger = logging.getLogger(__name__)

class WorkspaceCoordinatorAgent:
    def __init__(self, model_client: BaseLlm, mcp_toolset: McpToolset):
        self.model_client = model_client
        self.mcp_toolset = mcp_toolset
        self.evidence_store: Dict[str, Any] = {}
        
        # Specialists initialized later after tools are fetched, 
        # OR we pass tools dynamically during execution?
        # ADK Agents typically register tools at init or runtime.
        # Let's initialize specialists here but we need to register tools BEFORE running them.
        
        self.specialists = {
            "MailAnalystAgent": MailAnalystAgent(model_client),
            "CalendarAnalystAgent": CalendarAnalystAgent(model_client),
            "DriveAnalystAgent": DriveAnalystAgent(model_client),
        }
        
    async def initialize(self):
        """
        Fetches tools from MCP and registers them with specialists.
        This must be called before run().
        """
        tools = await self.mcp_toolset.get_adk_tools()
        logger.info(f"Discovered {len(tools)} tools from MCP.")
        
        # Distribute tools.
        # Strategy: Give ALL tools to ALL specialists for now (Simple Auto-Discovery).
        # Optimization: Filter by name prefix (e.g. if tool name starts with 'mail_').
        for name, agent in self.specialists.items():
            for tool in tools:
                 agent.add_tool(tool)
            logger.info(f"Registered {len(tools)} tools with {name}")

    async def run(self, user_query: str) -> str:
        """
        Main execution loop.
        """
        logger.info(f"Coordinator received query: {user_query}")
        
        # 1. Plan
        task_spec = await self._plan(user_query)
        logger.info(f"Generated TaskSpec: {task_spec}")
        
        # 2. Execute Steps
        for step in task_spec.steps:
            logger.info(f"Executing step: {step.step_id} - {step.name}")
            try:
                result = await self._execute_step(step)
                self.evidence_store[step.step_id] = result
                # Update step outputs
                step.outputs = result
            except Exception as e:
                logger.error(f"Step {step.step_id} failed: {e}", exc_info=True)
                # Fail gracefully or implement retry here (as per design)
                # For now, mark as failed
                self.evidence_store[step.step_id] = {"error": str(e)}
                break # Stop execution on failure
            
        # 3. Synthesize
        try:
            final_response = await self._synthesize(user_query, task_spec)
            return final_response
        except Exception as e:
             logger.error(f"Synthesis failed: {e}", exc_info=True)
             return "I encountered an error while synthesizing the response."

    async def _plan(self, query: str) -> TaskSpec:
        """
        Generates a TaskSpec from the user query.
        """
        prompt = f"""
        You are the Workspace Coordinator Agent.
        Your goal is to create a structured execution plan (TaskSpec) to answer the user's request.
        
        # User Query
        {query}
        
        # Available Agents
        - MailAnalystAgent: Specialized in searching, reading, and summarizing emails.
        - CalendarAnalystAgent: Specialized in finding meetings, checking schedules, and managing events.
        - DriveAnalystAgent: Specialized in searching for files and folders in OneDrive.
        
        # Instructions
        1. Analyze the user's intent.
        2. Break it down into logical steps.
        3. Assign each step to the most appropriate agent.
        4. Define clear inputs for each step.
        5. Output ONLY valid JSON adhering to the TaskSpec schema below.
        
        # Schema Example
        {{
            "intent": "summarize_emails",
            "steps": [
                {{
                    "step_id": "S1",
                    "name": "Fetch recent emails",
                    "assigned_agent": "MailAnalystAgent",
                    "inputs": {{ "time_window": "yesterday", "sender": "John Doe" }}
                }}
            ]
        }}
        """
        
        # Mocking the LLM call for now or using the model client
        # response = await self.model_client.generate(prompt)
        # return TaskSpec(**json.loads(response.text))
        
        # For scaffolding, we return a mock plan if the model isn't fully wired
        # But we should try to use the model. I will assume model_client works.
        try:
            response = await self.model_client.generate(prompt)
            # Basic parsing - in prod we need robust JSON extraction
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
                
            data = json.loads(text)
            
            steps = [Step(**s) for s in data.get("steps", [])]
            return TaskSpec(
                intent=data.get("intent", "unknown"),
                steps=steps,
                entities=data.get("entities", []),
                time_window=data.get("time_window"),
                actions=data.get("actions", [])
            )
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            # Fallback mock for testing "Summarize emails"
            if "email" in query.lower():
                 return TaskSpec(
                    intent="summarize_emails",
                    steps=[
                        Step(step_id="S1", name="List Emails", assigned_agent="MailAnalystAgent")
                    ]
                )
            return TaskSpec(intent="unknown")

    async def _execute_step(self, step: Step) -> Dict[str, Any]:
        agent = self.specialists.get(step.assigned_agent)
        if not agent:
            return {"error": f"Unknown agent {step.assigned_agent}"}
        
        # Construct prompt for the specialist
        context = f"Step: {step.name}. Inputs: {step.inputs}. Previous Evidence: {self.evidence_store}"
        
        # Call the specialist agent
        # We need to ensure the agent has the tools registered (handled in initialize)
        logger.info(f"Invoking {step.assigned_agent} for step {step.name}")
        
        response = await agent.run(context)
        return {"status": "executed", "output": response.text}

    async def _synthesize(self, query: str, task_spec: TaskSpec) -> str:
        prompt = f"""
        Construct a final answer for the user based on the evidence.
        Query: {query}
        Evidence: {self.evidence_store}
        """
        response = await self.model_client.generate(prompt)
        return response.text
