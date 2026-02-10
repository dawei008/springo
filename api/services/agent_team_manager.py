"""
Springo Agent Team Manager
多 Agent 团队协作服务 - 动态任务分解、流式并行执行、结果合成
"""
import json
import uuid
import logging
import asyncio
from typing import AsyncGenerator, Dict, Any, Optional, List
from datetime import datetime

from ..models.teams import (
    Team, TeamAgent, TaskBoardItem, AgentRole,
    TeamSpawnRequest, ROLE_CONFIGS,
)
from .bedrock import get_bedrock_service, BedrockService
from .model_registry import get_model_info
from .session_state import get_working_dir
from ..utils.streaming import SSEEventBuilder

logger = logging.getLogger(__name__)


def _with_working_dir(system_prompt: str) -> str:
    """Append working directory and SPRINGO.md reference to system prompt."""
    from ..utils.springo_md import load_springo_md
    parts = [system_prompt]
    springo_md = load_springo_md()
    if springo_md:
        parts.append(f"\n\n{springo_md}")
    wd = get_working_dir()
    if wd:
        import os
        springo_config_dir = os.path.expanduser("~/.springo")
        parts.append(
            f"\n\n## Working Directory & Springo Config\n"
            f"- **Working Directory**: `{wd}` — project code lives here\n"
            f"- **Springo Config**: `{springo_config_dir}/` — settings, skills, sessions, scripts\n"
            f"  - Skills: `{springo_config_dir}/skills/` (each subfolder has SKILL.md)\n"
        )
    return "".join(parts)


def _build_body(model_name: str, max_tokens: int, system: str, messages: list) -> dict:
    """Build a Bedrock request body with conditional anthropic_version."""
    info = get_model_info(model_name)
    api_format = info["api_format"] if info else "anthropic"
    body: dict = {
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if api_format == "anthropic":
        body["anthropic_version"] = "bedrock-2023-05-31"
    return body


def _get_api_format(model_name: str) -> str:
    """Return 'anthropic' or 'converse' for *model_name*."""
    info = get_model_info(model_name)
    return info["api_format"] if info else "anthropic"


class AgentTeamManager:
    """Agent 团队管理器 - 协调多个 Agent 并行工作"""

    def __init__(self, bedrock: BedrockService = None):
        self.bedrock = bedrock or get_bedrock_service()
        self._teams: Dict[str, Team] = {}

    def get_team(self, team_id: str) -> Optional[Team]:
        return self._teams.get(team_id)

    def spawn_team(self, request: TeamSpawnRequest) -> Team:
        """Create a new team based on the user request"""
        team = Team(
            user_request=request.user_request,
            shared_context=request.context or "",
        )

        # Always add an orchestrator
        orchestrator_role = ROLE_CONFIGS["orchestrator"].model_copy()
        orchestrator_role.model = request.model
        team.agents.append(TeamAgent(role=orchestrator_role))

        self._teams[team.team_id] = team
        logger.info(f"Team spawned: {team.team_id} for request: {request.user_request[:80]}")
        return team

    async def execute_team(
        self,
        team_id: str,
        max_parallel: int = 3
    ) -> AsyncGenerator[str, None]:
        """
        Execute the team workflow via SSE streaming with real-time deltas:
        1. Orchestrator dynamically decomposes the task (1-6 agents)
        2. Spawn worker agents and execute with streaming via queue
        3. Orchestrator synthesizes results with streaming
        """
        team = self._teams.get(team_id)
        if not team:
            yield SSEEventBuilder.team_error(team_id, "Team not found")
            yield SSEEventBuilder.done()
            return

        try:
            # === Phase 1: Emit team spawned ===
            agent_info = [
                {"agent_id": a.agent_id, "role": a.role.name, "purpose": a.role.purpose}
                for a in team.agents
            ]
            yield SSEEventBuilder.team_spawned(team.team_id, agent_info, team.user_request)

            # === Phase 2: Orchestrator decomposes the task ===
            team.status = "planning"
            yield SSEEventBuilder.team_planning(team.team_id)

            orchestrator = team.agents[0]
            orchestrator.status = "thinking"

            subtasks = await self._decompose_task(orchestrator, team.user_request, team.shared_context)

            if not subtasks:
                yield SSEEventBuilder.team_error(team.team_id, "Orchestrator failed to decompose task")
                yield SSEEventBuilder.done()
                return

            # Create task board
            for st in subtasks:
                task_item = TaskBoardItem(
                    title=st.get("title", "Untitled"),
                    description=st.get("description", ""),
                )
                team.task_board.append(task_item)

            # Spawn worker agents for each subtask (supports custom roles)
            for i, st in enumerate(subtasks):
                role_name = st.get("role", "explorer")
                custom_instructions = st.get("custom_instructions", "")
                agent_model = st.get("model", "")

                if role_name in ROLE_CONFIGS:
                    role_config = ROLE_CONFIGS[role_name].model_copy()
                else:
                    # Create custom role from explorer template
                    base = ROLE_CONFIGS["explorer"].model_copy()
                    role_config = AgentRole(
                        name=role_name,
                        purpose=custom_instructions[:100] if custom_instructions else f"Custom {role_name} agent",
                        system_prompt=custom_instructions or base.system_prompt,
                        model=base.model,
                        tools_available=base.tools_available,
                    )

                # Override model if orchestrator specified one
                if agent_model:
                    role_config.model = agent_model

                agent = TeamAgent(
                    role=role_config,
                    custom_instructions=custom_instructions,
                    assigned_task=team.task_board[i].task_id,
                )
                team.agents.append(agent)
                team.task_board[i].assigned_to = agent.agent_id

            orchestrator.status = "complete"

            # Emit task board
            task_board_data = [
                {
                    "task_id": t.task_id,
                    "title": t.title,
                    "description": t.description,
                    "assigned_to": t.assigned_to,
                    "role": next(
                        (a.role.name for a in team.agents if a.agent_id == t.assigned_to),
                        "unknown"
                    ),
                    "status": t.status,
                }
                for t in team.task_board
            ]
            yield SSEEventBuilder.team_task_board(team.team_id, task_board_data)

            # === Phase 3: Execute worker agents with streaming queue ===
            team.status = "executing"
            worker_agents = [a for a in team.agents if a.role.name != "orchestrator"]

            # Queue-based streaming execution
            event_queue: asyncio.Queue = asyncio.Queue()
            completed_count = 0
            total_agents = len(worker_agents)

            async def run_agent_streaming(agent: TeamAgent):
                """Run a single agent and push events to queue"""
                task_item = next(
                    (t for t in team.task_board if t.assigned_to == agent.agent_id),
                    None
                )
                task_title = task_item.title if task_item else "Unknown"

                # Push start event
                await event_queue.put(
                    SSEEventBuilder.team_agent_start(
                        team.team_id, agent.agent_id, agent.role.name, task_title
                    )
                )

                try:
                    full_text, tokens = await self._execute_agent_streaming(
                        team, agent, task_item, team.user_request, team.shared_context,
                        event_queue
                    )
                    agent.status = "complete"
                    agent.findings = full_text
                    agent.token_usage = tokens
                    if task_item:
                        task_item.status = "complete"
                        task_item.findings = full_text

                    await event_queue.put(
                        SSEEventBuilder.team_agent_complete(
                            team.team_id, agent.agent_id, agent.role.name,
                            task_title, full_text, tokens
                        )
                    )
                except Exception as e:
                    agent.status = "error"
                    agent.findings = f"Error: {str(e)}"
                    agent.completed_at = datetime.now().isoformat()
                    if task_item:
                        task_item.status = "error"
                        task_item.findings = agent.findings
                    await event_queue.put(
                        SSEEventBuilder.team_agent_error(
                            team.team_id, agent.agent_id, agent.role.name, str(e)
                        )
                    )

                # Signal this agent is done
                await event_queue.put({"__agent_done__": True})

            # Launch agents in batches of max_parallel
            running_tasks: List[asyncio.Task] = []
            agent_index = 0

            # Start first batch
            while agent_index < total_agents and agent_index < max_parallel:
                task = asyncio.create_task(run_agent_streaming(worker_agents[agent_index]))
                running_tasks.append(task)
                agent_index += 1

            # Drain queue and yield events until all agents complete
            while completed_count < total_agents:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=15.0)

                    if isinstance(event, dict) and event.get("__agent_done__"):
                        completed_count += 1
                        # Launch next agent if any remaining
                        if agent_index < total_agents:
                            task = asyncio.create_task(run_agent_streaming(worker_agents[agent_index]))
                            running_tasks.append(task)
                            agent_index += 1
                    else:
                        yield event

                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield SSEEventBuilder.heartbeat(0.0)

            # Wait for all tasks to finish (they should already be done)
            for task in running_tasks:
                if not task.done():
                    try:
                        await asyncio.wait_for(task, timeout=5.0)
                    except (asyncio.TimeoutError, Exception):
                        pass

            # === Phase 4: Orchestrator synthesizes results with streaming ===
            team.status = "synthesizing"
            yield SSEEventBuilder.team_synthesizing(team.team_id)

            final_result = ""
            async for event in self._synthesize_results_streaming(orchestrator, team):
                if isinstance(event, dict) and "__final_result__" in event:
                    final_result = event["__final_result__"]
                else:
                    yield event  # SSE event string

            team.status = "complete"
            team.final_result = final_result
            team.completed_at = datetime.now().isoformat()

            # Calculate total tokens
            for agent in team.agents:
                team.total_tokens["input_tokens"] += agent.token_usage.get("input_tokens", 0)
                team.total_tokens["output_tokens"] += agent.token_usage.get("output_tokens", 0)

            yield SSEEventBuilder.team_complete(
                team.team_id, final_result, team.total_tokens
            )
            yield SSEEventBuilder.done()

        except Exception as e:
            logger.error(f"Team execution error: {e}", exc_info=True)
            team.status = "error"
            yield SSEEventBuilder.team_error(team.team_id, str(e))
            yield SSEEventBuilder.done()

    async def _decompose_task(
        self, orchestrator: TeamAgent, user_request: str, context: str
    ) -> List[Dict[str, Any]]:
        """Use orchestrator to dynamically decompose a request into subtasks.

        The orchestrator decides:
        - How many agents (1-6) based on task complexity
        - Which roles to use (built-in or custom)
        - Optional custom_instructions per agent
        - Optional model override per agent
        """
        messages = [
            {
                "role": "user",
                "content": (
                    "Decompose the following user request into subtasks for a team of AI agents.\n\n"
                    "GUIDELINES:\n"
                    "- Use 1-6 agents depending on complexity. Simple questions may need only 1 agent.\n"
                    "- Available built-in roles: explorer, researcher, implementer, reviewer\n"
                    "- You may also create custom role names (e.g., 'data_analyst', 'security_auditor', 'translator')\n"
                    "- For custom roles, provide 'custom_instructions' with the agent's system prompt\n"
                    "- Optionally specify 'model' per agent (e.g., 'claude-sonnet-4-5-20250929' for complex tasks)\n\n"
                    f"User request: {user_request}\n"
                    f"{'Additional context: ' + context if context else ''}\n\n"
                    "Respond with ONLY a JSON array. Each item has:\n"
                    '- "title": short task title\n'
                    '- "description": what this agent should do\n'
                    '- "role": role name (built-in or custom)\n'
                    '- "custom_instructions": (optional) system prompt for custom roles\n'
                    '- "model": (optional) model override\n\n'
                    "Example:\n"
                    '[{"title": "Research API docs", "description": "Find the latest API documentation...", "role": "researcher"}]\n'
                ),
            }
        ]

        model_id = self.bedrock.get_bedrock_model_id(orchestrator.role.model)
        body = _build_body(
            orchestrator.role.model, 2048,
            _with_working_dir(orchestrator.role.system_prompt), messages,
        )
        orch_api_format = _get_api_format(orchestrator.role.model)

        try:
            response = await self.bedrock.invoke_model(model_id, body, api_format=orch_api_format)
            content = response.get("content", [])
            text = ""
            for block in content:
                if block.get("type") == "text":
                    text += block.get("text", "")

            orchestrator.token_usage = {
                "input_tokens": response.get("usage", {}).get("input_tokens", 0),
                "output_tokens": response.get("usage", {}).get("output_tokens", 0),
            }

            # Parse JSON from response - try to extract JSON array
            text = text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(
                    line for line in lines
                    if not line.strip().startswith("```")
                )
                text = text.strip()

            # Find JSON array in text
            start = text.find("[")
            end = text.rfind("]")
            if start >= 0 and end > start:
                text = text[start:end + 1]

            subtasks = json.loads(text)
            if not isinstance(subtasks, list):
                subtasks = [subtasks]

            # Clamp to 1-6 agents
            if len(subtasks) > 6:
                subtasks = subtasks[:6]

            logger.info(f"Orchestrator decomposed into {len(subtasks)} subtasks")
            return subtasks

        except Exception as e:
            logger.error(f"Task decomposition failed: {e}")
            return []

    async def _execute_agent_streaming(
        self,
        team: Team,
        agent: TeamAgent,
        task_item: Optional[TaskBoardItem],
        user_request: str,
        shared_context: str,
        event_queue: asyncio.Queue,
    ) -> tuple:
        """Execute a single agent's task with streaming, pushing delta events to queue.

        Returns:
            (full_text, tokens_dict)
        """
        agent.status = "thinking"
        agent.started_at = datetime.now().isoformat()

        if task_item:
            task_item.status = "in_progress"

        task_desc = task_item.description if task_item else user_request
        task_title = task_item.title if task_item else "General task"

        # Gather findings from other completed agents as context
        other_findings = []
        for other in team.agents:
            if other.agent_id != agent.agent_id and other.findings:
                other_findings.append(f"[{other.role.name}] {other.findings[:500]}")

        # Build system prompt (use custom_instructions if set)
        system_prompt = agent.role.system_prompt
        if agent.custom_instructions and agent.custom_instructions != system_prompt:
            system_prompt = agent.custom_instructions + "\n\n" + system_prompt

        messages = [
            {
                "role": "user",
                "content": (
                    f"You are working as part of a team to address this request:\n"
                    f"Original request: {user_request}\n\n"
                    f"Your specific task: {task_title}\n"
                    f"Details: {task_desc}\n"
                    f"{'Shared context: ' + shared_context if shared_context else ''}\n"
                    f"{'Other agents findings: ' + chr(10).join(other_findings) if other_findings else ''}\n\n"
                    f"Provide your findings concisely. Focus on your assigned task.\n"
                    f"Do NOT use emojis or icons. Use plain text and markdown only."
                ),
            }
        ]

        model_id = self.bedrock.get_bedrock_model_id(agent.role.model)
        body = _build_body(
            agent.role.model, 4096,
            _with_working_dir(system_prompt), messages,
        )
        agent_api_format = _get_api_format(agent.role.model)

        agent.status = "executing"
        full_text = ""
        tokens = {"input_tokens": 0, "output_tokens": 0}

        try:
            async for chunk in self.bedrock.invoke_model_stream_text(model_id, body, api_format=agent_api_format):
                if chunk["type"] == "delta":
                    text = chunk["text"]
                    full_text += text
                    # Push delta event to queue
                    await event_queue.put(
                        SSEEventBuilder.team_agent_delta(
                            team.team_id, agent.agent_id, agent.role.name, text
                        )
                    )
                elif chunk["type"] == "usage":
                    tokens["input_tokens"] += chunk.get("input_tokens", 0)
                    tokens["output_tokens"] += chunk.get("output_tokens", 0)

            agent.completed_at = datetime.now().isoformat()
            return full_text, tokens

        except Exception as e:
            agent.completed_at = datetime.now().isoformat()
            raise

    async def _execute_agent(
        self,
        team: Team,
        agent: TeamAgent,
        task_item: Optional[TaskBoardItem],
        user_request: str,
        shared_context: str,
    ) -> Dict[str, Any]:
        """Execute a single agent's task (non-streaming fallback)"""
        agent.status = "thinking"
        agent.started_at = datetime.now().isoformat()

        if task_item:
            task_item.status = "in_progress"

        task_desc = task_item.description if task_item else user_request
        task_title = task_item.title if task_item else "General task"

        other_findings = []
        for other in team.agents:
            if other.agent_id != agent.agent_id and other.findings:
                other_findings.append(f"[{other.role.name}] {other.findings[:500]}")

        messages = [
            {
                "role": "user",
                "content": (
                    f"You are working as part of a team to address this request:\n"
                    f"Original request: {user_request}\n\n"
                    f"Your specific task: {task_title}\n"
                    f"Details: {task_desc}\n"
                    f"{'Shared context: ' + shared_context if shared_context else ''}\n"
                    f"{'Other agents findings: ' + chr(10).join(other_findings) if other_findings else ''}\n\n"
                    f"Provide your findings concisely. Focus on your assigned task.\n"
                    f"Do NOT use emojis or icons. Use plain text and markdown only."
                ),
            }
        ]

        model_id = self.bedrock.get_bedrock_model_id(agent.role.model)
        body = _build_body(
            agent.role.model, 4096,
            _with_working_dir(agent.role.system_prompt), messages,
        )
        ea_api_format = _get_api_format(agent.role.model)

        try:
            agent.status = "executing"
            response = await self.bedrock.invoke_model(model_id, body, api_format=ea_api_format)
            content = response.get("content", [])
            text = ""
            for block in content:
                if block.get("type") == "text":
                    text += block.get("text", "")

            agent.completed_at = datetime.now().isoformat()
            tokens = {
                "input_tokens": response.get("usage", {}).get("input_tokens", 0),
                "output_tokens": response.get("usage", {}).get("output_tokens", 0),
            }

            return {"findings": text, "tokens": tokens}

        except Exception as e:
            agent.completed_at = datetime.now().isoformat()
            raise

    async def _synthesize_results_streaming(
        self, orchestrator: TeamAgent, team: Team
    ) -> AsyncGenerator:
        """Orchestrator synthesizes results with streaming deltas.

        Yields SSE event strings for deltas, then yields the final full text (non-string).
        """
        findings_text = ""
        for agent in team.agents:
            if agent.role.name != "orchestrator" and agent.findings:
                task_item = next(
                    (t for t in team.task_board if t.assigned_to == agent.agent_id),
                    None
                )
                task_title = task_item.title if task_item else "General"
                findings_text += f"\n### [{agent.role.name}] {task_title}\n{agent.findings}\n"

        messages = [
            {
                "role": "user",
                "content": (
                    f"You are the orchestrator. Synthesize the following agent findings into "
                    f"a clear, comprehensive response to the user's original request.\n\n"
                    f"Original request: {team.user_request}\n\n"
                    f"Agent findings:\n{findings_text}\n\n"
                    f"Provide a well-organized synthesis. Do not simply concatenate the findings. "
                    f"Create a coherent response that addresses the user's request completely.\n\n"
                    f"IMPORTANT: Do NOT use any emojis or icons in the output. Use plain text and markdown formatting only."
                ),
            }
        ]

        model_id = self.bedrock.get_bedrock_model_id(orchestrator.role.model)
        body = _build_body(
            orchestrator.role.model, 8192,
            _with_working_dir(orchestrator.role.system_prompt), messages,
        )
        synth_api_format = _get_api_format(orchestrator.role.model)

        full_text = ""
        try:
            async for chunk in self.bedrock.invoke_model_stream_text(model_id, body, api_format=synth_api_format):
                if chunk["type"] == "delta":
                    text = chunk["text"]
                    full_text += text
                    yield SSEEventBuilder.team_synthesis_delta(team.team_id, text)
                elif chunk["type"] == "usage":
                    orchestrator.token_usage["input_tokens"] += chunk.get("input_tokens", 0)
                    orchestrator.token_usage["output_tokens"] += chunk.get("output_tokens", 0)

            # Yield final result as a dict sentinel
            yield {"__final_result__": full_text}

        except Exception as e:
            logger.error(f"Streaming synthesis failed: {e}")
            fallback = f"[Synthesis failed: {e}]\n\nRaw findings:\n{findings_text}"
            yield {"__final_result__": fallback}

    async def _synthesize_results(self, orchestrator: TeamAgent, team: Team) -> str:
        """Orchestrator synthesizes all agent findings (non-streaming fallback)"""
        findings_text = ""
        for agent in team.agents:
            if agent.role.name != "orchestrator" and agent.findings:
                task_item = next(
                    (t for t in team.task_board if t.assigned_to == agent.agent_id),
                    None
                )
                task_title = task_item.title if task_item else "General"
                findings_text += f"\n### [{agent.role.name}] {task_title}\n{agent.findings}\n"

        messages = [
            {
                "role": "user",
                "content": (
                    f"You are the orchestrator. Synthesize the following agent findings into "
                    f"a clear, comprehensive response to the user's original request.\n\n"
                    f"Original request: {team.user_request}\n\n"
                    f"Agent findings:\n{findings_text}\n\n"
                    f"Provide a well-organized synthesis. Do not simply concatenate the findings. "
                    f"Create a coherent response that addresses the user's request completely.\n\n"
                    f"IMPORTANT: Do NOT use any emojis or icons in the output. Use plain text and markdown formatting only."
                ),
            }
        ]

        model_id = self.bedrock.get_bedrock_model_id(orchestrator.role.model)
        body = _build_body(
            orchestrator.role.model, 8192,
            _with_working_dir(orchestrator.role.system_prompt), messages,
        )
        synth_ns_api_format = _get_api_format(orchestrator.role.model)

        try:
            response = await self.bedrock.invoke_model(model_id, body, api_format=synth_ns_api_format)
            content = response.get("content", [])
            text = ""
            for block in content:
                if block.get("type") == "text":
                    text += block.get("text", "")

            usage = response.get("usage", {})
            orchestrator.token_usage["input_tokens"] += usage.get("input_tokens", 0)
            orchestrator.token_usage["output_tokens"] += usage.get("output_tokens", 0)

            return text

        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return f"[Synthesis failed: {e}]\n\nRaw findings:\n{findings_text}"


# Singleton
_team_manager: Optional[AgentTeamManager] = None


def get_team_manager() -> AgentTeamManager:
    global _team_manager
    if _team_manager is None:
        _team_manager = AgentTeamManager()
    return _team_manager
