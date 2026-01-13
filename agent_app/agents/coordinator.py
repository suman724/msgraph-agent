"""
WorkspaceCoordinatorAgent - Refactored to use Google ADK multi-agent constructs.

This module implements the main orchestrator for the MSGraph Agent using:
- ParallelAgent: For concurrent retrieval from Mail, Calendar, and Drive specialists
- LoopAgent: For course correction/retry loops with the Critic
- Agent with sub_agents: For hierarchical delegation

Architecture:
    User Query
        |
        v
    CoordinatorAgent (LlmAgent with planner)
        |
        +---> ParallelAgent (Retrieval)
        |         |---> MailAnalystAgent
        |         |---> CalendarAnalystAgent
        |         +---> DriveAnalystAgent
        |
        +---> LoopAgent (Validation)
                  |---> SynthesisAgent
                  +---> CriticAgent (escalate on PASS)
"""

import json
import logging
from typing import Dict, Any, List, Optional
import uuid

from google.adk import Agent
from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents.loop_agent import LoopAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.models import BaseLlm
from google.adk.tools.function_tool import FunctionTool

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


def create_parallel_retrieval_agent(
    mail_agent: Agent,
    calendar_agent: Agent,
    drive_agent: Agent
) -> ParallelAgent:
    """
    Creates a ParallelAgent that runs Mail, Calendar, and Drive 
    specialists concurrently for retrieval tasks.
    
    This replaces the custom _execute_steps_parallel() method.
    """
    return ParallelAgent(
        name="ParallelRetrievalAgent",
        description="Runs domain specialists in parallel to gather evidence from Mail, Calendar, and Drive.",
        sub_agents=[mail_agent, calendar_agent, drive_agent]
    )


def create_validation_loop_agent(
    synthesis_agent: Agent,
    critic_agent: Agent,
    max_iterations: int = MAX_RETRY_ATTEMPTS
) -> LoopAgent:
    """
    Creates a LoopAgent for the validation/course-correction cycle.
    
    The loop continues until:
    - CriticAgent returns PASS (triggers escalation to exit loop)
    - max_iterations is reached
    
    This replaces the custom _validate_with_critic() recursive method.
    """
    return LoopAgent(
        name="ValidationLoopAgent",
        description="Iteratively synthesizes and validates responses until quality criteria are met.",
        sub_agents=[synthesis_agent, critic_agent],
        max_iterations=max_iterations
    )


class WorkspaceCoordinatorAgent:
    """
    The main coordinator agent that orchestrates the workspace query pipeline.
    
    Uses ADK multi-agent constructs:
    - ParallelAgent for concurrent retrieval (fan-out)
    - LoopAgent for validation cycles (course correction)
    - SequentialAgent for the main pipeline
    
    The coordinator still maintains:
    - Evidence store for collected data
    - Local tools for time parsing, person resolution, etc.
    - Write executor for side-effect operations
    """
    
    def __init__(self, model_client: BaseLlm, mcp_toolset: McpToolset):
        """
        Initialize the coordinator with model client and MCP toolset.
        
        Args:
            model_client: The LLM client for generation
            mcp_toolset: The MCP toolset for MS Graph operations
        """
        self.model_client = model_client
        self.mcp_toolset = mcp_toolset
        self.evidence_store: Dict[str, Any] = {}
        
        # Initialize session service for ADK Runner
        self.session_service = InMemorySessionService()
        
        # ------------------------------------------------------------
        # Domain Specialist Agents (ADK Agents)
        # These are LLM-based agents for specific domains
        # ------------------------------------------------------------
        self.mail_agent = MailAnalystAgent(model_client)
        self.calendar_agent = CalendarAnalystAgent(model_client)
        self.drive_agent = DriveAnalystAgent(model_client)
        
        # Legacy dict for backward compatibility
        self.specialists = {
            "MailAnalystAgent": self.mail_agent,
            "CalendarAnalystAgent": self.calendar_agent,
            "DriveAnalystAgent": self.drive_agent,
        }
        
        # ------------------------------------------------------------
        # Support Agents
        # ------------------------------------------------------------
        self.report_writer = ReportWriterAgent(model_client)
        self.critic = CriticAgent(model_client)
        
        # ------------------------------------------------------------
        # Multi-Agent Constructs (ADK orchestration primitives)
        # ------------------------------------------------------------
        # ParallelAgent for concurrent retrieval
        self.retrieval_agent = create_parallel_retrieval_agent(
            self.mail_agent,
            self.calendar_agent,
            self.drive_agent
        )
        
        # Synthesis agent for composing final response
        self.synthesis_agent = Agent(
            model=model_client,
            name="SynthesisAgent",
            instruction=(
                "You are the Synthesis Agent. Your role is to compose a clear, "
                "comprehensive response from the collected evidence.\n\n"
                "You will receive evidence from Mail, Calendar, and Drive queries.\n"
                "Synthesize this into a coherent, well-structured response.\n"
                "Be concise but complete. Cite sources when relevant."
            )
        )
        
        # LoopAgent for validation cycle
        self.validation_loop = create_validation_loop_agent(
            self.synthesis_agent,
            self.critic,
            max_iterations=MAX_RETRY_ATTEMPTS
        )
        
        # ------------------------------------------------------------
        # Main Pipeline: Sequential Agent combining all stages
        # ------------------------------------------------------------
        self.main_pipeline = SequentialAgent(
            name="MainPipelineAgent",
            description="Main orchestration pipeline: Retrieval -> Synthesis -> Validation",
            sub_agents=[
                self.retrieval_agent,
                self.validation_loop
            ]
        )
        
        # ------------------------------------------------------------
        # Write Executor (non-LLM helper for side effects)
        # ------------------------------------------------------------
        self.write_executor = WriteExecutor(mcp_toolset)
        
        # ------------------------------------------------------------
        # Local Tools (coordinator-level, deterministic)
        # ------------------------------------------------------------
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
            if hasattr(agent, 'tools') and isinstance(agent.tools, list):
                agent.tools.extend(tools)
            logger.info(f"Registered {len(tools)} tools with {name}")

    async def run(self, user_query: str) -> str:
        """
        Main execution entry point.
        
        Uses the ADK Runner to execute the main pipeline which:
        1. Runs parallel retrieval (ParallelAgent)
        2. Synthesizes and validates (LoopAgent)
        
        Args:
            user_query: The user's natural language query
            
        Returns:
            The final response string
        """
        # Reset evidence store for this run
        self.evidence_store = {}
        logger.info(f"Coordinator received query: {user_query}")
        
        # Create a Runner for the main pipeline
        runner = Runner(
            agent=self.main_pipeline,
            app_name="MsgraphAgent",
            session_service=self.session_service
        )
        
        # Simple content wrapper for Runner
        class SimpleContent:
            def __init__(self, text):
                self.role = "user"
                self.parts = [text]
        
        # Execute the pipeline
        response_text = ""
        session_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=SimpleContent(user_query)
            ):
                # Capture response events
                if hasattr(event, "text") and event.text:
                    response_text += event.text
                elif hasattr(event, "content") and event.content:
                    response_text += str(event.content)
                    
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            # Fallback to legacy execution
            return await self._legacy_run(user_query)
        
        # If pipeline didn't produce output, fallback to legacy
        if not response_text.strip():
            logger.warning("Pipeline produced no output, falling back to legacy execution")
            return await self._legacy_run(user_query)
            
        return response_text

    async def _legacy_run(self, user_query: str) -> str:
        """
        Legacy execution path for backward compatibility.
        
        This method preserves the original orchestration logic
        in case the ADK pipeline doesn't work as expected.
        """
        from ..schemas.task_spec import TaskSpec, Step
        
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

    # ----------------------------------------------------------------
    # Helper Methods (preserved from original implementation)
    # ----------------------------------------------------------------
    
    async def _run_agent(self, agent: Agent, query: str) -> str:
        """Run an ADK agent using a Runner."""
        runner = Runner(
            agent=agent,
            app_name="MsgraphAgent",
            session_service=self.session_service
        )
        
        class SimpleContent:
            def __init__(self, text):
                self.role = "user"
                self.parts = [text]
                
        response_text = ""
        try:
            session_id = str(uuid.uuid4())
            user_id = str(uuid.uuid4())
            
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=SimpleContent(query)
            ):
                if hasattr(event, "text") and event.text:
                    response_text += event.text
                elif hasattr(event, "content") and event.content:
                    response_text += str(event.content)
                     
        except Exception as e:
            logger.error(f"Error running agent {agent.name}: {e}")
            return f"Error: {str(e)}"
            
        return response_text

    async def _execute_steps_parallel(self, steps: List) -> None:
        """
        Executes steps with parallel fan-out for independent steps.
        (Legacy method - kept for backward compatibility)
        """
        import asyncio
        from ..schemas.task_spec import Step
        
        completed = set()
        pending_steps = list(steps)
        
        while pending_steps:
            runnable = []
            still_pending = []
            
            for step in pending_steps:
                deps = set(step.depends_on)
                if deps.issubset(completed):
                    runnable.append(step)
                else:
                    still_pending.append(step)
            
            if not runnable:
                logger.error("No runnable steps - possible circular dependency")
                break
            
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

    async def _execute_step_with_retry(self, step, attempt: int = 1) -> Dict[str, Any]:
        """Executes a step with course correction on failure/empty results."""
        result = await self._execute_step(step)
        
        if self._is_empty_result(result) and attempt < MAX_RETRY_ATTEMPTS:
            logger.info(f"Empty result for step {step.step_id}, applying course correction (attempt {attempt})")
            
            retry_policy = step.retry_policy or {}
            on_empty = retry_policy.get("on_empty", "expand_time_window")
            
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
        words = current.split()
        if len(words) > 1:
            return " ".join(words[1:])
        return current

    def _needs_report(self, task_spec) -> bool:
        """Determines if the task requires a formal report."""
        report_keywords = ["report", "status", "summary report", "weekly report"]
        return any(kw in task_spec.intent.lower() for kw in report_keywords)

    async def _generate_report(self, query: str) -> str:
        """Generates a report using the ReportWriterAgent."""
        context = f"Generate a report for: {query}\nEvidence: {json.dumps(self.evidence_store)}"
        result = await self._run_agent(self.report_writer, context)
        return result

    async def _validate_with_critic(self, query: str, response: str, attempt: int = 1) -> str:
        """Validates the response with the CriticAgent."""
        verdict = await self.critic.validate(query, self.evidence_store, response)
        
        if verdict.get("verdict") == "PASS":
            logger.info("Critic validation: PASS")
            return response
        
        if attempt >= MAX_RETRY_ATTEMPTS:
            logger.warning(f"Critic validation failed after {attempt} attempts, returning best effort")
            return response + "\n\n[Note: This response may be incomplete. Issues: " + str(verdict.get("issues", [])) + "]"
        
        logger.info(f"Critic validation: FAIL - {verdict.get('issues')}. Attempting correction.")
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

    async def _plan(self, query: str):
        """Generates a TaskSpec from the user query."""
        from ..schemas.task_spec import TaskSpec, Step
        
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
            if "email" in query.lower():
                return TaskSpec(
                    intent="summarize_emails",
                    steps=[
                        Step(step_id="S1", name="List Emails", assigned_agent="MailAnalystAgent")
                    ]
                )
            return TaskSpec(intent="unknown")

    async def _execute_step(self, step) -> Dict[str, Any]:
        """Executes a single step by delegating to the appropriate agent."""
        agent = self.specialists.get(step.assigned_agent)
        if not agent:
            if step.assigned_agent == "ReportWriterAgent":
                return {"output": await self._generate_report(step.inputs.get("query", ""))}
            return {"error": f"Unknown agent {step.assigned_agent}"}
        
        context = f"Step: {step.name}. Inputs: {step.inputs}. Previous Evidence: {self.evidence_store}"
        
        logger.info(f"Invoking {step.assigned_agent} for step {step.name}")
        
        output_text = await self._run_agent(agent, context)
        return {"status": "executed", "output": output_text}

    async def _synthesize(self, query: str, task_spec) -> str:
        """Synthesizes a final response from collected evidence."""
        prompt = f"""
        Construct a final answer for the user based on the evidence.
        Query: {query}
        Evidence: {self.evidence_store}
        """
        response = await self.model_client.generate(prompt)
        return response.text
