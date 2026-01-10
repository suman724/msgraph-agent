import json
import asyncio
from google.adk.models import BaseLlm
import logging
from typing import Dict, Any, List, Optional
from google.adk import Agent
from ..schemas.task_spec import TaskSpec, Step
from .mail_agent import MailAnalystAgent
from .calendar_agent import CalendarAnalystAgent
from .drive_agent import DriveAnalystAgent
from .report_writer import ReportWriterAgent
from .critic import CriticAgent
from .write_executor import WriteExecutor
from ..mcp.toolset import McpToolset
from ..tools.time_window import parse_time_window
from ..tools.person_resolver import resolve_person
from ..tools.extraction import extract_action_items

# Setup logging
logger = logging.getLogger(__name__)

# Maximum retry attempts for course correction
MAX_RETRY_ATTEMPTS = 3

class WorkspaceCoordinatorAgent:
    def __init__(self, model_client: BaseLlm, mcp_toolset: McpToolset):
        self.model_client = model_client
        self.mcp_toolset = mcp_toolset
        self.evidence_store: Dict[str, Any] = {}
        
        # Domain specialists
        self.specialists = {
            "MailAnalystAgent": MailAnalystAgent(model_client),
            "CalendarAnalystAgent": CalendarAnalystAgent(model_client),
            "DriveAnalystAgent": DriveAnalystAgent(model_client),
        }
        
        # Additional agents
        self.report_writer = ReportWriterAgent(model_client)
        self.critic = CriticAgent(model_client)
        
        # Write executor (non-LLM helper)
        self.write_executor = WriteExecutor(mcp_toolset)
        
        # Local tools (coordinator-level)
        self.local_tools = {
            "parse_time_window": parse_time_window,
            "resolve_person": resolve_person,
            "extract_action_items": extract_action_items,
        }
        
    async def initialize(self):
        """
        Fetches tools from MCP and registers them with specialists.
        This must be called before run().
        """
        tools = await self.mcp_toolset.get_adk_tools()
        logger.info(f"Discovered {len(tools)} tools from MCP.")
        
        # Distribute tools to domain specialists
        for name, agent in self.specialists.items():
            for tool in tools:
                 agent.add_tool(tool)
            logger.info(f"Registered {len(tools)} tools with {name}")

    async def run(self, user_query: str) -> str:
        """
        Main execution loop with course correction and validation.
        """
        # Reset evidence store for this run
        self.evidence_store = {}
        logger.info(f"Coordinator received query: {user_query}")
        
        # 1. Plan
        task_spec = await self._plan(user_query)
        logger.info(f"Generated TaskSpec: {task_spec}")
        
        # 2. Execute Steps (with parallel fan-out for independent steps)
        await self._execute_steps_parallel(task_spec.steps)
            
        # 3. Check if we need a report
        if self._needs_report(task_spec):
            report = await self._generate_report(user_query)
            self.evidence_store["report"] = report
        
        # 4. Synthesize initial response
        initial_response = await self._synthesize(user_query, task_spec)
        
        # 5. Validate with Critic (course correction loop)
        final_response = await self._validate_with_critic(user_query, initial_response)
        
        return final_response

    async def _execute_steps_parallel(self, steps: List[Step]):
        """
        Executes steps with parallel fan-out for independent steps.
        Steps with dependencies wait for their dependencies to complete.
        """
        completed = set()
        pending_steps = list(steps)
        
        while pending_steps:
            # Find steps that can run now (no unmet dependencies)
            runnable = []
            still_pending = []
            
            for step in pending_steps:
                deps = set(step.depends_on)
                if deps.issubset(completed):
                    runnable.append(step)
                else:
                    still_pending.append(step)
            
            if not runnable:
                # Deadlock or circular dependency
                logger.error("No runnable steps - possible circular dependency")
                break
            
            # Execute runnable steps in parallel
            if len(runnable) > 1:
                logger.info(f"Parallel fan-out: executing {len(runnable)} steps")
                tasks = [self._execute_step_with_retry(step) for step in runnable]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for step, result in zip(runnable, results):
                    if isinstance(result, Exception):
                        logger.error(f"Step {step.step_id} failed: {result}")
                        self.evidence_store[step.step_id] = {"error": str(result)}
                    else:
                        self.evidence_store[step.step_id] = result
                        step.outputs = result
                    completed.add(step.step_id)
            else:
                # Single step - execute directly
                step = runnable[0]
                try:
                    result = await self._execute_step_with_retry(step)
                    self.evidence_store[step.step_id] = result
                    step.outputs = result
                except Exception as e:
                    logger.error(f"Step {step.step_id} failed: {e}")
                    self.evidence_store[step.step_id] = {"error": str(e)}
                completed.add(step.step_id)
            
            pending_steps = still_pending

    async def _execute_step_with_retry(self, step: Step, attempt: int = 1) -> Dict[str, Any]:
        """
        Executes a step with course correction on failure/empty results.
        """
        result = await self._execute_step(step)
        
        # Course correction: check for empty/failed results
        if self._is_empty_result(result) and attempt < MAX_RETRY_ATTEMPTS:
            logger.info(f"Empty result for step {step.step_id}, applying course correction (attempt {attempt})")
            
            # Apply retry policy from step or default
            retry_policy = step.retry_policy or {}
            on_empty = retry_policy.get("on_empty", "expand_time_window")
            
            # Modify inputs based on retry policy
            if on_empty == "expand_time_window":
                step.inputs["time_window"] = self._expand_time_window(step.inputs.get("time_window", "1 day"))
            elif on_empty == "broaden_query":
                step.inputs["query"] = self._broaden_query(step.inputs.get("query", ""))
            elif on_empty == "resolve_person":
                person = step.inputs.get("person")
                if person:
                    resolved = self.local_tools["resolve_person"](person)
                    step.inputs["person_email"] = resolved.get("email")
            
            return await self._execute_step_with_retry(step, attempt + 1)
        
        return result

    def _is_empty_result(self, result: Dict[str, Any]) -> bool:
        """Checks if a result is empty or contains no useful data."""
        if "error" in result:
            return True
        output = result.get("output", "")
        if not output or output.strip() == "" or output == "[]" or output == "{}":
            return True
        return False

    def _expand_time_window(self, current: str) -> str:
        """Expands time window for retry (1 day -> 7 days -> 30 days)."""
        expansions = {
            "1 day": "7 days",
            "yesterday": "7 days",
            "7 days": "30 days",
            "30 days": "90 days",
        }
        return expansions.get(current, "30 days")

    def _broaden_query(self, current: str) -> str:
        """Broadens a search query for retry."""
        # Simple implementation: remove first word if multi-word
        words = current.split()
        if len(words) > 1:
            return " ".join(words[1:])
        return current

    def _needs_report(self, task_spec: TaskSpec) -> bool:
        """Determines if the task requires a formal report."""
        report_keywords = ["report", "status", "summary report", "weekly report"]
        return any(kw in task_spec.intent.lower() for kw in report_keywords)

    async def _generate_report(self, query: str) -> str:
        """Generates a report using the ReportWriterAgent."""
        context = f"Generate a report for: {query}\nEvidence: {json.dumps(self.evidence_store)}"
        result = await self.report_writer.run(context)
        return result.text if hasattr(result, 'text') else str(result)

    async def _validate_with_critic(self, query: str, response: str, attempt: int = 1) -> str:
        """
        Validates the response with the CriticAgent.
        Applies course correction if validation fails.
        """
        verdict = await self.critic.validate(query, self.evidence_store, response)
        
        if verdict.get("verdict") == "PASS":
            logger.info("Critic validation: PASS")
            return response
        
        if attempt >= MAX_RETRY_ATTEMPTS:
            logger.warning(f"Critic validation failed after {attempt} attempts, returning best effort")
            return response + "\n\n[Note: This response may be incomplete. Issues: " + str(verdict.get("issues", [])) + "]"
        
        # Course correction based on Critic feedback
        logger.info(f"Critic validation: FAIL - {verdict.get('issues')}. Attempting correction.")
        issues = verdict.get("issues", [])
        
        # Try to address issues
        for issue in issues:
            issue_lower = issue.lower()
            if "time" in issue_lower or "date" in issue_lower:
                # Need more specific time data - retry relevant steps
                pass  # Would trigger step re-execution with expanded time
            elif "missing" in issue_lower or "incomplete" in issue_lower:
                # Need more data - could trigger additional retrieval
                pass
        
        # Re-synthesize with feedback
        response = await self._synthesize_with_feedback(query, verdict.get("issues", []))
        return await self._validate_with_critic(query, response, attempt + 1)

    async def _synthesize_with_feedback(self, query: str, issues: List[str]) -> str:
        """Synthesizes a response taking into account Critic feedback."""
        prompt = f"""
        Construct a final answer for the user based on the evidence.
        Query: {query}
        Evidence: {self.evidence_store}
        
        Previous issues to address: {issues}
        Please ensure your response addresses these issues.
        """
        response = await self.model_client.generate(prompt)
        return response.text

    async def _plan(self, query: str) -> TaskSpec:
        """
        Generates a TaskSpec from the user query.
        """
        # First, use local tools to parse any time references
        time_window = None
        for phrase in ["yesterday", "last week", "today", "last 7 days", "last month"]:
            if phrase in query.lower():
                time_window = self.local_tools["parse_time_window"](phrase)
                break
        
        prompt = f"""
        You are the Workspace Coordinator Agent.
        Your goal is to create a structured execution plan (TaskSpec) to answer the user's request.
        
        # User Query
        {query}
        
        # Parsed Time Window
        {time_window if time_window else "Not specified"}
        
        # Available Agents
        - MailAnalystAgent: Specialized in searching, reading, and summarizing emails.
        - CalendarAnalystAgent: Specialized in finding meetings, checking schedules, and managing events.
        - DriveAnalystAgent: Specialized in searching for files and folders in OneDrive.
        - ReportWriterAgent: Specialized in composing structured reports from evidence.
        
        # Instructions
        1. Analyze the user's intent.
        2. Break it down into logical steps.
        3. Assign each step to the most appropriate agent.
        4. Define clear inputs for each step.
        5. Specify dependencies between steps using "depends_on" (list of step_ids).
        6. For potentially empty results, specify a "retry_policy" with "on_empty" action.
        7. Output ONLY valid JSON adhering to the TaskSpec schema below.
        
        # Schema Example
        {{
            "intent": "summarize_emails",
            "steps": [
                {{
                    "step_id": "S1",
                    "name": "Fetch recent emails",
                    "assigned_agent": "MailAnalystAgent",
                    "inputs": {{ "time_window": "yesterday", "sender": "John Doe" }},
                    "depends_on": [],
                    "retry_policy": {{ "on_empty": "expand_time_window", "max_attempts": 3 }}
                }},
                {{
                    "step_id": "S2",
                    "name": "Check calendar for related meetings",
                    "assigned_agent": "CalendarAnalystAgent",
                    "inputs": {{ "time_window": "yesterday" }},
                    "depends_on": [],
                    "retry_policy": {{ "on_empty": "expand_time_window" }}
                }}
            ]
        }}
        """
        
        try:
            response = await self.model_client.generate(prompt)
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
                time_window=time_window or data.get("time_window"),
                actions=data.get("actions", [])
            )
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            # Fallback mock for testing
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
            # Check if it's a ReportWriter step
            if step.assigned_agent == "ReportWriterAgent":
                return await self._generate_report(step.inputs.get("query", ""))
            return {"error": f"Unknown agent {step.assigned_agent}"}
        
        # Construct prompt for the specialist
        context = f"Step: {step.name}. Inputs: {step.inputs}. Previous Evidence: {self.evidence_store}"
        
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
