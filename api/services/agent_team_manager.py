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
from .vendor_router import get_vendor_router
from .model_registry import get_model_info, get_model_limits
from .session_state import get_working_dir
from .mcp_manager import get_mcp_manager
from .context_manager import (
    truncate_tool_results, prepare_messages_for_api,
    count_messages_tokens, MAX_INLINE_OUTPUT_SIZE,
)
from ..utils.streaming import SSEEventBuilder
from ..config import settings

logger = logging.getLogger(__name__)

# Transient Bedrock error patterns worth retrying
_RETRIABLE_ERRORS = (
    "ThrottlingException",
    "ServiceUnavailableException",
    "InternalServerException",
    "ModelTimeoutException",
    "Too Many Requests",
    "Connection reset",
    "Read timed out",
    "ExpiredTokenException",
    "ExpiredToken",
    "InvalidIdentityToken",
    "UnrecognizedClientException",
)

# Subset that indicates credential expiry — triggers session refresh
_CREDENTIAL_ERRORS = (
    "ExpiredTokenException",
    "ExpiredToken",
    "InvalidIdentityToken",
    "UnrecognizedClientException",
)


async def _retry_bedrock_call(coro_factory, *, label: str = "bedrock"):
    """Retry a Bedrock API call with exponential backoff for transient errors.

    *coro_factory* is a zero-arg callable that returns a new awaitable each
    time (because awaitables are consumed on first await).

    On credential expiry errors, refreshes the bedrock session before retrying.

    Returns the result on success, raises on permanent failure.
    """
    max_retries = settings.team_bedrock_max_retries
    base_delay = settings.team_bedrock_retry_base_delay

    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            msg = str(exc)
            if attempt < max_retries and any(pat in msg for pat in _RETRIABLE_ERRORS):
                # Refresh session on credential errors
                if any(pat in msg for pat in _CREDENTIAL_ERRORS):
                    try:
                        svc = get_bedrock_service()
                        svc.refresh_session()
                        logger.warning(f"[{label}] Credential expired, refreshed session")
                    except Exception as refresh_err:
                        logger.error(f"[{label}] Failed to refresh session: {refresh_err}")
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"[{label}] Transient error (attempt {attempt + 1}/{max_retries + 1}): "
                    f"{msg[:120]} — retrying in {delay:.1f}s"
                )
                await asyncio.sleep(delay)
            else:
                raise
    raise last_exc  # type: ignore[misc]


# Compact LTM snippet injected into every team-agent system prompt so that
# worker agents can retrieve user preferences / interests when relevant.
_TEAM_LTM_SNIPPET = (
    "\n\n## Long-Term Memory (LTM)\n"
    "You can retrieve the user's stored preferences and interests via execute_command:\n"
    "```\n"
    "execute_command(\"python ~/.springo/skills/memory/scripts/memory.py get USER_PREFERENCE --limit 5\")\n"
    "execute_command(\"python ~/.springo/skills/memory/scripts/memory.py search '关键词' --top-k 5\")\n"
    "```\n"
    "If the task involves the user's interests, preferences, or personalization, "
    "retrieve memory FIRST before doing other work.\n"
)


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


def _build_body(model_name: str, max_tokens: int, system: str, messages: list,
                 tools: list = None) -> dict:
    """Build a vendor-appropriate request body.

    For Anthropic/Converse (Bedrock): returns Anthropic-shaped body.
    For OpenAI (DeepSeek direct): returns OpenAI-shaped body with converted messages.
    """
    from .model_registry import get_vendor_model_id
    info = get_model_info(model_name)
    api_format = info["api_format"] if info else "anthropic"

    if api_format == "openai":
        # OpenAI format (DeepSeek direct, etc.)
        openai_messages = [{"role": "system", "content": system}]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, str):
                openai_messages.append({"role": role, "content": content})
            elif isinstance(content, list):
                # Convert Anthropic content blocks to OpenAI format
                text_parts = []
                tool_calls = []
                tool_results = []
                for block in content:
                    btype = block.get("type", "")
                    if btype == "text":
                        text_parts.append(block.get("text", ""))
                    elif btype == "tool_use":
                        import json as _json
                        tool_calls.append({
                            "id": block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": _json.dumps(block.get("input", {})),
                            },
                        })
                    elif btype == "tool_result":
                        result_content = block.get("content", "")
                        if isinstance(result_content, list):
                            result_content = " ".join(
                                b.get("text", "") for b in result_content if b.get("type") == "text"
                            )
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": block.get("tool_use_id", ""),
                            "content": str(result_content),
                        })

                if role == "assistant":
                    msg_dict = {"role": "assistant"}
                    if text_parts:
                        msg_dict["content"] = "".join(text_parts)
                    if tool_calls:
                        msg_dict["tool_calls"] = tool_calls
                        if "content" not in msg_dict:
                            msg_dict["content"] = None
                    openai_messages.append(msg_dict)
                elif role == "user" and tool_results:
                    # tool_result blocks become separate tool messages
                    for tr in tool_results:
                        openai_messages.append(tr)
                else:
                    openai_messages.append({"role": role, "content": "".join(text_parts)})

        body = {
            "model": get_vendor_model_id(model_name),
            "max_tokens": max_tokens,
            "messages": openai_messages,
            "_original_model": model_name,
        }
        if tools:
            # Convert Anthropic tools to OpenAI function format
            openai_tools = []
            for t in tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": t.get("name", ""),
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {}),
                    },
                })
            body["tools"] = openai_tools
        return body

    # Anthropic / Converse format (Bedrock)
    body: dict = {
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if api_format == "anthropic":
        body["anthropic_version"] = "bedrock-2023-05-31"
    if tools:
        body["tools"] = tools
    # Carry the short model name so bedrock.py can register beta headers
    body["_original_model"] = model_name
    return body


def _get_api_format(model_name: str) -> str:
    """Return 'anthropic' or 'converse' for *model_name*."""
    info = get_model_info(model_name)
    return info["api_format"] if info else "anthropic"


class AgentTeamManager:
    """Agent 团队管理器 - 协调多个 Agent 并行工作"""

    def __init__(self, bedrock=None):
        # Use VendorRouter so non-Bedrock models (e.g. deepseek-v3.2-direct)
        # are dispatched to the correct vendor service.
        self.bedrock = bedrock or get_vendor_router()
        self._teams: Dict[str, Team] = {}
        self._running_tasks: Dict[str, List[asyncio.Task]] = {}  # team_id -> agent tasks
        self._cleanup_task: Optional[asyncio.Task] = None

    def get_team(self, team_id: str) -> Optional[Team]:
        return self._teams.get(team_id)

    def cancel_team(self, team_id: str) -> None:
        """Cancel all running agent tasks for a team (e.g., on client disconnect)."""
        tasks = self._running_tasks.pop(team_id, [])
        for task in tasks:
            if not task.done():
                task.cancel()
        team = self._teams.get(team_id)
        if team and team.status not in ("complete", "error"):
            team.status = "error"
            team.completed_at = datetime.now().isoformat()
        logger.info(f"Team {team_id} cancelled ({len(tasks)} tasks)")

    def _register_tasks(self, team_id: str, tasks: List[asyncio.Task]) -> None:
        """Register running agent tasks for cleanup on disconnect."""
        self._running_tasks[team_id] = tasks

    def _unregister_tasks(self, team_id: str) -> None:
        """Remove task tracking after normal completion."""
        self._running_tasks.pop(team_id, None)

    def cleanup_completed_teams(self) -> int:
        """Remove completed teams older than team_completed_cleanup_secs. Returns count removed."""
        cutoff = settings.team_completed_cleanup_secs
        now = datetime.now()
        to_remove = []
        for tid, team in self._teams.items():
            if team.status in ("complete", "error") and team.completed_at:
                try:
                    completed = datetime.fromisoformat(team.completed_at)
                    if (now - completed).total_seconds() > cutoff:
                        to_remove.append(tid)
                except (ValueError, TypeError):
                    pass
        for tid in to_remove:
            del self._teams[tid]
            self._running_tasks.pop(tid, None)
            # Also clean up orphaned message bus and task manager
            from .message_bus import remove_bus
            from .team_task_manager import remove_task_manager
            remove_bus(tid)
            remove_task_manager(tid)
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} completed teams")
        return len(to_remove)

    @staticmethod
    def _resolve_model(request_model: str) -> str:
        """Resolve team model: use request model, or fall back to main agent's configured model."""
        if request_model:
            return request_model
        # Fall back to the main agent's default model (from settings / bedrock_model_id)
        from .model_registry import MODEL_REGISTRY
        # settings.bedrock_model_id is a full bedrock ID like "us.anthropic.claude-opus-4-6-v1"
        # Find the short name that maps to it
        for short_name, info in MODEL_REGISTRY.items():
            if info.get("bedrock_id") == settings.bedrock_model_id:
                return short_name
        # If no match, try stripping common prefixes to get a usable name
        return settings.bedrock_model_id

    def spawn_team(self, request: TeamSpawnRequest) -> Team:
        """Create a new team based on the user request"""
        mode = getattr(request, "mode", "classic")
        resolved_model = self._resolve_model(request.model)

        team = Team(
            user_request=request.user_request,
            shared_context=request.context or "",
            execution_mode=mode,
        )

        # Always add an orchestrator / team lead
        orchestrator_role = ROLE_CONFIGS["orchestrator"].model_copy()
        orchestrator_role.model = resolved_model
        team.agents.append(TeamAgent(
            role=orchestrator_role,
            name="team-lead" if mode == "collaborative" else "",
        ))

        self._teams[team.team_id] = team

        # For collaborative mode, set up message bus and task manager
        if mode == "collaborative":
            from .message_bus import get_or_create_bus
            from .team_task_manager import get_or_create_task_manager
            bus = get_or_create_bus(team.team_id)
            bus.register_agent("team-lead")
            get_or_create_task_manager(team.team_id, bus)

        logger.info(f"Team spawned: {team.team_id} mode={mode} for request: {request.user_request[:80]}")
        return team

    async def execute_team(
        self,
        team_id: str,
    ) -> AsyncGenerator[str, None]:
        """
        Execute the team workflow via SSE streaming with real-time deltas.

        For classic mode:
          1. Orchestrator dynamically decomposes the task (1-6 agents)
          2. Launch ALL worker agents simultaneously (no artificial cap)
          3. Orchestrator synthesizes results with streaming

        For collaborative mode:
          Long-lived agents with message passing and shared task board.
        """
        team = self._teams.get(team_id)
        if not team:
            yield SSEEventBuilder.team_error(team_id, "Team not found")
            yield SSEEventBuilder.done()
            return

        # Guard against double-execution (e.g., frontend reconnect re-POSTing)
        if team.status in ("planning", "executing", "synthesizing"):
            logger.warning(
                f"[Team:{team_id}] execute_team called while already {team.status}, "
                f"rejecting duplicate execution"
            )
            yield SSEEventBuilder.team_error(
                team_id, f"Team is already {team.status}. Use GET /events to reconnect."
            )
            yield SSEEventBuilder.done()
            return

        # Branch on execution mode
        if team.execution_mode == "collaborative":
            async for event in self.execute_team_collaborative(team_id):
                yield event
            return

        try:
            # === Phase 1: Emit team spawned ===
            agent_info = [
                {"agent_id": a.agent_id, "role": a.role.name, "purpose": a.role.purpose}
                for a in team.agents
            ]
            yield SSEEventBuilder.team_spawned(team.team_id, agent_info, team.user_request)

            # === Phase 2: Orchestrator decomposes the task (with tool access) ===
            team.status = "planning"
            yield SSEEventBuilder.team_planning(team.team_id)

            orchestrator = team.agents[0]
            orchestrator.status = "thinking"

            # Run decomposition in a task so we can drain tool events in real-time
            orch_queue: asyncio.Queue = asyncio.Queue()
            _decompose_result: List[Dict[str, Any]] = []

            async def _run_decompose():
                result = await self._decompose_task(
                    orchestrator, team.user_request, team.shared_context,
                    team, orch_queue,
                )
                _decompose_result.extend(result)
                await orch_queue.put({"__decompose_done__": True})

            decompose_task = asyncio.create_task(_run_decompose())

            # Drain orchestrator tool events while it plans
            while True:
                try:
                    event = await asyncio.wait_for(orch_queue.get(), timeout=15.0)
                    if isinstance(event, dict) and event.get("__decompose_done__"):
                        break
                    yield event
                except asyncio.TimeoutError:
                    yield SSEEventBuilder.heartbeat(0.0)
                    if decompose_task.done():
                        break

            # Ensure the task is complete
            if not decompose_task.done():
                await decompose_task

            subtasks = _decompose_result
            orchestrator.status = "complete"

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
            # All workers use the same model as the orchestrator (= user's active model)
            # unless the orchestrator explicitly overrides per-agent.
            team_model = team.agents[0].role.model  # orchestrator's resolved model
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

                # Use team model (= user's active model) unless orchestrator explicitly overrides
                role_config.model = agent_model if agent_model else team_model

                agent = TeamAgent(
                    role=role_config,
                    custom_instructions=custom_instructions,
                    assigned_task=team.task_board[i].task_id,
                )
                team.agents.append(agent)
                team.task_board[i].assigned_to = agent.agent_id

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
            event_queue: asyncio.Queue = asyncio.Queue(maxsize=settings.team_event_queue_max)
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

            # Launch ALL agents simultaneously — no artificial parallel cap.
            # The orchestrator already decided how many agents are needed.
            running_tasks: List[asyncio.Task] = []
            for agent in worker_agents:
                task = asyncio.create_task(run_agent_streaming(agent))
                running_tasks.append(task)
            self._register_tasks(team.team_id, running_tasks)

            # Drain queue and yield events until all agents complete
            while completed_count < total_agents:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=15.0)

                    if isinstance(event, dict) and event.get("__agent_done__"):
                        completed_count += 1
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

            self._unregister_tasks(team.team_id)
            yield SSEEventBuilder.team_complete(
                team.team_id, final_result, team.total_tokens
            )
            yield SSEEventBuilder.done()

        except asyncio.CancelledError:
            logger.warning(f"Team {team.team_id} execution cancelled")
            self._unregister_tasks(team.team_id)
            team.status = "error"
            team.completed_at = datetime.now().isoformat()
            yield SSEEventBuilder.team_error(team.team_id, "Team execution cancelled")
            yield SSEEventBuilder.done()
        except Exception as e:
            logger.error(f"Team execution error: {e}", exc_info=True)
            self._unregister_tasks(team.team_id)
            team.status = "error"
            yield SSEEventBuilder.team_error(team.team_id, str(e))
            yield SSEEventBuilder.done()

    # Max orchestrator tool iterations during decomposition.
    # The orchestrator should PLAN, not EXPLORE — tools are only for memory
    # retrieval.  3 iterations: 1 potential memory call + 2 to produce JSON.
    _ORCH_MAX_TOOL_ITERATIONS = 3

    @staticmethod
    def _parse_subtasks_json(text: str) -> List[Dict[str, Any]]:
        """Extract a JSON array of subtasks from model output text."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(
                line for line in lines if not line.strip().startswith("```")
            )
            text = text.strip()

        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            text = text[start : end + 1]

        subtasks = json.loads(text)
        if not isinstance(subtasks, list):
            subtasks = [subtasks]

        # Clamp to 1-10 agents
        if len(subtasks) > 10:
            subtasks = subtasks[:10]
        return subtasks

    async def _decompose_task(
        self,
        orchestrator: TeamAgent,
        user_request: str,
        context: str,
        team: Team,
        event_queue: Optional[asyncio.Queue] = None,
    ) -> List[Dict[str, Any]]:
        """Use orchestrator to dynamically decompose a request into subtasks.

        The orchestrator has full tool access (like Claude Code's team lead)
        so it can retrieve user preferences, read files, etc. before planning.
        """
        working_dir = get_working_dir() or ""
        decompose_prompt = (
            "Decompose the following user request into subtasks for a team of AI agents.\n\n"
            "IMPORTANT: Your job is to PLAN, not to EXPLORE. "
            "Worker agents will do the actual exploration and execution.\n"
            "Only use tools if the request specifically involves user preferences/personalization "
            "(retrieve memory first via execute_command with memory.py). "
            "For all other requests, go directly to decomposition.\n\n"
            + (f"Project working directory: {working_dir}\n"
               "Worker agents will operate in this directory.\n\n" if working_dir else "")
            + "GUIDELINES:\n"
            "- Use 1-10 agents depending on complexity. Simple questions may need only 1 agent.\n"
            "- IMPORTANT: If the user's request implies parallel dimensions (e.g., 'each continent', "
            "'each module', 'compare A vs B vs C'), create ONE agent PER dimension. "
            "Maximize parallelism — prefer more focused agents over fewer broad ones.\n"
            "- Available built-in roles: explorer, researcher, implementer, reviewer\n"
            "- You may also create custom role names (e.g., 'data_analyst', 'security_auditor', 'translator')\n"
            "- For custom roles, provide 'custom_instructions' with the agent's system prompt\n"
            "- Optionally specify 'model' per agent (e.g., 'claude-sonnet-4-5-20250929' for complex tasks)\n"
            "- When you have user preferences/interests from memory, include them in each agent's description "
            "so agents can personalize their work.\n\n"
            f"User request: {user_request}\n"
            f"{'Additional context: ' + context if context else ''}\n\n"
            "When ready, respond with ONLY a JSON array. Each item has:\n"
            '- "title": short task title\n'
            '- "description": what this agent should do (include user preferences if retrieved)\n'
            '- "role": role name (built-in or custom)\n'
            '- "custom_instructions": (optional) system prompt for custom roles\n'
            '- "model": (optional) model override\n\n'
            "Example:\n"
            '[{"title": "Research API docs", "description": "Find the latest API documentation...", "role": "researcher"}]\n'
        )

        messages = [{"role": "user", "content": decompose_prompt}]

        # Build system prompt with LTM + working dir
        system_prompt = _with_working_dir(
            orchestrator.role.system_prompt + _TEAM_LTM_SNIPPET
        )

        model_id = self.bedrock.get_bedrock_model_id(orchestrator.role.model)
        orch_api_format = _get_api_format(orchestrator.role.model)

        # Load a limited tool set for orchestrator decomposition.
        # Only lightweight tools for memory retrieval and basic project awareness.
        # Heavy exploration (read_file, grep, glob, etc.) is left to worker agents.
        _ORCH_ALLOWED_TOOLS = {"execute_command", "list_directory"}
        tools = []
        try:
            mcp_mgr = await get_mcp_manager()
            tool_defs = mcp_mgr.get_tool_definitions()
            if tool_defs:
                tools = [
                    t.model_dump() if hasattr(t, "model_dump") else t
                    for t in tool_defs
                ]
                tools = [t for t in tools if t.get("name") in _ORCH_ALLOWED_TOOLS]
        except Exception as e:
            logger.warning(f"Orchestrator: failed to load tools: {e}")

        try:
            for iteration in range(1, self._ORCH_MAX_TOOL_ITERATIONS + 1):
                body = _build_body(
                    orchestrator.role.model, 4096, system_prompt, messages,
                    tools=tools if tools else None,
                )

                response = await _retry_bedrock_call(
                    lambda b=body: self.bedrock.invoke_model(model_id, b, api_format=orch_api_format),
                    label="orchestrator",
                )
                content = response.get("content", [])
                usage = response.get("usage", {})
                orchestrator.token_usage["input_tokens"] += usage.get("input_tokens", 0)
                orchestrator.token_usage["output_tokens"] += usage.get("output_tokens", 0)

                # Separate text and tool_use blocks
                text_parts = []
                tool_uses = []
                for block in content:
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_uses.append(block)

                if not tool_uses:
                    # No tool calls — parse JSON from text
                    full_text = "".join(text_parts)
                    subtasks = self._parse_subtasks_json(full_text)
                    logger.info(
                        f"Orchestrator decomposed into {len(subtasks)} subtasks "
                        f"(after {iteration} iteration(s))"
                    )
                    return subtasks

                # --- Execute tools and continue the loop ---
                messages.append({"role": "assistant", "content": content})
                tool_results = []

                for tu in tool_uses:
                    tool_name = tu.get("name", "")
                    tool_input = tu.get("input", {})
                    tool_id = tu.get("id", "")

                    if event_queue:
                        await event_queue.put(
                            SSEEventBuilder.team_agent_tool(
                                team.team_id, orchestrator.agent_id,
                                "orchestrator", tool_name, "start",
                            )
                        )

                    try:
                        mcp_mgr = await get_mcp_manager()
                        result = await asyncio.wait_for(
                            mcp_mgr.execute_tool(tool_name, tool_input),
                            timeout=60.0,
                        )
                        result_str = (
                            json.dumps(result, ensure_ascii=False)
                            if isinstance(result, (dict, list))
                            else str(result)
                        )
                        is_error = False
                    except Exception as e:
                        result_str = f"Error: {e}"
                        is_error = True

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result_str[:8000],
                        **({"is_error": True} if is_error else {}),
                    })

                    if event_queue:
                        await event_queue.put(
                            SSEEventBuilder.team_agent_tool(
                                team.team_id, orchestrator.agent_id,
                                "orchestrator", tool_name,
                                "error" if is_error else "complete",
                                result_str[:200],
                            )
                        )

                    logger.info(
                        f"Orchestrator tool {tool_name}: "
                        f"{'error' if is_error else 'ok'}"
                    )

                messages.append({"role": "user", "content": tool_results})

            # Exhausted iterations — try to parse whatever text accumulated so far
            logger.warning("Orchestrator exhausted tool iterations, attempting to parse accumulated text")
            for msg in reversed(messages):
                if msg.get("role") == "assistant":
                    msg_content = msg.get("content", [])
                    if isinstance(msg_content, list):
                        for block in msg_content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                subtasks = self._parse_subtasks_json(block.get("text", ""))
                                if subtasks:
                                    logger.info(f"Recovered {len(subtasks)} subtasks from accumulated text")
                                    return subtasks
            return []

        except Exception as e:
            logger.error(f"Task decomposition failed: {e}")
            return []

    # Maximum tool iterations per agent to prevent infinite loops
    AGENT_MAX_TOOL_ITERATIONS = 15

    async def _execute_agent_streaming(
        self,
        team: Team,
        agent: TeamAgent,
        task_item: Optional[TaskBoardItem],
        user_request: str,
        shared_context: str,
        event_queue: asyncio.Queue,
    ) -> tuple:
        """Execute a single agent's task with streaming and tool support.

        Agents can call tools (MCP, built-in, skills) in a loop, similar to
        the ``messages_auto_api`` auto-loop.  The response is streamed via
        *event_queue* as ``team_agent_delta`` and ``team_agent_tool`` events.

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

        # Build system prompt (use custom_instructions if set, always append LTM)
        system_prompt = agent.role.system_prompt
        if agent.custom_instructions and agent.custom_instructions != system_prompt:
            system_prompt = agent.custom_instructions + "\n\n" + system_prompt
        system_prompt += _TEAM_LTM_SNIPPET

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
                    f"Use available tools to accomplish your task. When you have enough "
                    f"information, provide your findings concisely.\n"
                    f"Do NOT use emojis or icons. Use plain text and markdown only."
                ),
            }
        ]

        # ---- Load tools from MCPManager ----
        tools = []
        try:
            mcp_mgr = await get_mcp_manager()
            tool_defs = mcp_mgr.get_tool_definitions()
            if tool_defs:
                tools = [t.model_dump() if hasattr(t, "model_dump") else t for t in tool_defs]
                logger.info(f"Agent {agent.role.name}: loaded {len(tools)} tools")
        except Exception as e:
            logger.warning(f"Agent {agent.role.name}: failed to load tools: {e}")

        agent.status = "executing"
        full_text = ""
        tokens = {"input_tokens": 0, "output_tokens": 0}

        working_dir = get_working_dir() or None
        model_limits = get_model_limits(agent.role.model)

        try:
            for iteration in range(1, self.AGENT_MAX_TOOL_ITERATIONS + 1):
                # Layer 2: Truncate old tool results before each API call
                if iteration > 1:
                    messages = prepare_messages_for_api(messages, keep_recent=3)

                # Layer 3: Emergency truncation if approaching context limit
                current_tokens = count_messages_tokens(messages)
                max_ctx = model_limits.get("max_context_tokens", 200000)
                if current_tokens > max_ctx * 0.85:
                    logger.warning(
                        f"Agent {agent.role.name}: context at {current_tokens:,}/{max_ctx:,} tokens, "
                        f"forcing aggressive truncation"
                    )
                    messages = truncate_tool_results(messages, max_size=2048)

                # Build bedrock request using the standard converter (handles
                # tool formatting, time injection, and model-specific quirks)
                request_body = {
                    "model": agent.role.model,
                    "max_tokens": 4096,
                    "system": _with_working_dir(system_prompt),
                    "messages": messages,
                }
                _, bedrock_body = self.bedrock.convert_request_to_bedrock(
                    request_body,
                    include_tools=bool(tools),
                    tools=tools if tools else None,
                    working_dir=working_dir,
                )

                model_id = self.bedrock.get_bedrock_model_id(agent.role.model)
                agent_api_format = _get_api_format(agent.role.model)

                # ---- Stream response & parse SSE events ----
                content_blocks = []
                tool_uses = []
                stop_reason = None
                iter_text = ""

                async for event in self.bedrock.invoke_model_stream(
                    model_id, bedrock_body, agent.role.model, api_format=agent_api_format
                ):
                    if "data: " not in event:
                        continue
                    try:
                        data_str = event.split("data: ", 1)[1].strip()
                        if not data_str or data_str == "[DONE]":
                            continue
                        data = json.loads(data_str)
                    except Exception:
                        continue

                    evt_type = data.get("type")

                    if evt_type == "content_block_start":
                        block = data.get("content_block", {})
                        if block.get("type") == "tool_use":
                            entry = {
                                "type": "tool_use",
                                "id": block.get("id"),
                                "name": block.get("name"),
                                "input": {},
                            }
                            content_blocks.append(entry)
                            tool_uses.append(entry)
                        elif block.get("type") == "text":
                            content_blocks.append({"type": "text", "text": ""})

                    elif evt_type == "content_block_delta":
                        delta = data.get("delta", {})
                        if delta.get("type") == "input_json_delta" and tool_uses:
                            partial = delta.get("partial_json", "")
                            if partial:
                                tool_uses[-1]["_partial_input"] = (
                                    tool_uses[-1].get("_partial_input", "") + partial
                                )
                        elif delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                iter_text += text
                                full_text += text
                                if content_blocks and content_blocks[-1].get("type") == "text":
                                    content_blocks[-1]["text"] += text
                                await event_queue.put(
                                    SSEEventBuilder.team_agent_delta(
                                        team.team_id, agent.agent_id, agent.role.name, text
                                    )
                                )

                    elif evt_type == "message_delta":
                        delta = data.get("delta", {})
                        stop_reason = delta.get("stop_reason")
                        usage = data.get("usage", {})
                        if usage:
                            tokens["output_tokens"] += usage.get("output_tokens", 0)

                    elif evt_type == "message_start":
                        msg = data.get("message", {})
                        usage = msg.get("usage", {})
                        if usage:
                            tokens["input_tokens"] += usage.get("input_tokens", 0)

                # ---- No tool calls → done ----
                if stop_reason != "tool_use" or not tool_uses:
                    break

                # ---- Parse accumulated tool inputs ----
                for tool in tool_uses:
                    if "_partial_input" in tool:
                        try:
                            tool["input"] = json.loads(tool.pop("_partial_input"))
                        except Exception:
                            tool["input"] = {}

                # ---- Execute tools ----
                mcp_manager = await get_mcp_manager()
                tool_results = []

                for tool in tool_uses:
                    tool_name = tool["name"]
                    await event_queue.put(
                        SSEEventBuilder.team_agent_tool(
                            team.team_id, agent.agent_id, agent.role.name,
                            tool_name, "start",
                        )
                    )
                    t0 = asyncio.get_event_loop().time()
                    try:
                        result = await asyncio.wait_for(
                            mcp_manager.execute_tool(tool_name, tool.get("input", {})),
                            timeout=settings.tool_execution_timeout,
                        )
                        is_error = "error" in result
                    except asyncio.TimeoutError:
                        result = {"error": f"Tool timed out after {settings.tool_execution_timeout}s"}
                        is_error = True
                    except Exception as e:
                        result = {"error": str(e)}
                        is_error = True

                    elapsed = asyncio.get_event_loop().time() - t0
                    result_str = json.dumps(result) if isinstance(result, dict) else str(result)
                    logger.info(
                        f"Agent {agent.role.name} tool {tool_name}: "
                        f"{elapsed:.1f}s, error={is_error}"
                    )
                    await event_queue.put(
                        SSEEventBuilder.team_agent_tool(
                            team.team_id, agent.agent_id, agent.role.name,
                            tool_name, "error" if is_error else "complete",
                            result_str[:200],
                        )
                    )

                    # Layer 1: Truncate large tool results inline (matches main agent)
                    result_bytes = len(result_str.encode("utf-8"))
                    if result_bytes > MAX_INLINE_OUTPUT_SIZE:
                        preview = result_str[:500]
                        result_str = json.dumps({
                            "result_truncated": True,
                            "size": result_bytes,
                            "preview": preview,
                            "message": f"Result truncated ({result_bytes:,} bytes). Preview shown.",
                        })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool["id"],
                        "content": result_str,
                        "is_error": is_error,
                    })

                # ---- Append assistant + tool results for next iteration ----
                assistant_content = []
                for block in content_blocks:
                    if block.get("type") == "tool_use":
                        assistant_content.append({
                            "type": "tool_use",
                            "id": block["id"],
                            "name": block["name"],
                            "input": block.get("input", {}),
                        })
                    elif block.get("type") == "text" and block.get("text"):
                        assistant_content.append({
                            "type": "text",
                            "text": block["text"],
                        })
                messages.append({"role": "assistant", "content": assistant_content})
                messages.append({"role": "user", "content": tool_results})

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
            response = await _retry_bedrock_call(
                lambda: self.bedrock.invoke_model(model_id, body, api_format=ea_api_format),
                label=f"agent-{agent.role.name}",
            )
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
                if chunk["type"] == "heartbeat":
                    yield SSEEventBuilder.heartbeat(0.0)
                elif chunk["type"] == "delta":
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
            response = await _retry_bedrock_call(
                lambda: self.bedrock.invoke_model(model_id, body, api_format=synth_ns_api_format),
                label="synthesis",
            )
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

    # ================================================================
    # Collaborative Mode - Long-lived agents with message passing
    # ================================================================

    async def execute_team_collaborative(
        self,
        team_id: str,
    ) -> AsyncGenerator[str, None]:
        """Execute a collaborative team with long-lived agent loops.

        The team lead agent runs as a persistent loop, receiving messages,
        calling tools (including team communication tools), and coordinating
        worker agents. Worker agents can communicate with each other and
        the team lead via the message bus.

        SSE events are streamed in real-time from the message bus and
        individual agent loops.
        """
        from .message_bus import get_bus
        from .team_task_manager import get_task_manager as get_tm
        from .agent_loop import run_agent_loop

        team = self._teams.get(team_id)
        if not team:
            yield SSEEventBuilder.team_error(team_id, "Team not found")
            yield SSEEventBuilder.done()
            return

        bus = get_bus(team_id)
        task_mgr = get_tm(team_id)
        if not bus or not task_mgr:
            yield SSEEventBuilder.team_error(team_id, "Message bus or task manager not initialized")
            yield SSEEventBuilder.done()
            return

        try:
            # Emit team spawned
            agent_info = [
                {
                    "agent_id": a.agent_id,
                    "name": a.name,
                    "role": a.role.name,
                    "purpose": a.role.purpose,
                }
                for a in team.agents
            ]
            yield SSEEventBuilder.team_spawned(team.team_id, agent_info, team.user_request)

            team.status = "executing"
            yield SSEEventBuilder.team_planning(team.team_id)

            team_lead = team.agents[0]
            lead_mailbox = bus.get_mailbox(team_lead.name or "team-lead")

            if not lead_mailbox:
                lead_mailbox = bus.register_agent(team_lead.name or "team-lead")

            # Override the orchestrator system prompt for collaborative mode.
            # The default ROLE_CONFIGS["orchestrator"] prompt is for classic mode
            # (JSON array output). In collaborative mode the lead coordinates via
            # task_create / send_message / ask_user.
            #
            # The team lead only receives team tools (structural scoping in
            # run_agent_loop with team_tools_only=True), so we don't need to list
            # forbidden tools — the lead simply can't call them.
            team_lead.role.system_prompt = (
                "You are the team lead coordinating a collaborative agent team.\n\n"
                "## Your Workflow\n"
                "1. Analyze the user's request and break it into independent tasks using task_create\n"
                "2. Spawn workers for tasks using spawn_worker — each worker runs autonomously\n"
                "3. Workers will message you when they complete tasks\n"
                "4. Review results, create follow-up tasks and spawn more workers if needed\n"
                "5. When all work is done, synthesize the final answer for the user\n\n"
                "## How Workers Operate\n"
                "Workers are autonomous agents with full tool access — they can read files, "
                "execute commands, search the web, write code, and more. They handle all "
                "research, exploration, and implementation. Your job is to decompose, "
                "coordinate, and synthesize.\n\n"
                "## Task Design\n"
                "- Each task should be self-contained enough for a worker to complete independently\n"
                "- If the request has parallel dimensions (e.g., 'compare A vs B', 'each module'), "
                "create one task per dimension to maximize parallelism\n"
                "- Set dependencies with task_update when tasks must run in sequence\n"
                "- Include enough context in each task description for the worker to succeed\n\n"
                "## Spawning Workers\n"
                "- Use spawn_worker after creating tasks — provide a name and the task IDs\n"
                "- For independent tasks, spawn workers in parallel (call spawn_worker multiple times)\n"
                "- A single worker can handle multiple related tasks\n"
                "- Use descriptive names: 'researcher', 'implementer', 'reviewer'\n\n"
                "## Communication\n"
                "- Use send_message to give workers additional context or relay user feedback\n"
                "- Use ask_user when you need clarification from the user\n"
                "- Use send_message(type='shutdown_request') to shut down a worker when done\n\n"
                "## Idle Behavior\n"
                "After spawning workers, stop and wait. Workers will send you a message "
                "when they complete their tasks. You do not need to poll task_list — "
                "you will receive a notification for each completed task. Only call "
                "task_list when you need to check overall status after receiving a message.\n\n"
                "Do not use emojis in any output."
            )

            # Create initial message — just the user's request.
            # The system prompt already describes the team lead's workflow.
            from .message_bus import AgentMessage
            initial_msg = AgentMessage(
                type="message",
                sender="user",
                recipient=team_lead.name or "team-lead",
                content=(
                    f"{team.user_request}"
                    f"{chr(10) + chr(10) + 'Additional context: ' + team.shared_context if team.shared_context else ''}"
                ),
                summary="User request",
            )

            # Shared SSE event queue — agent loops push events here
            event_queue: asyncio.Queue = asyncio.Queue(maxsize=settings.team_event_queue_max)

            # Track spawned worker names to avoid duplicates
            spawned_workers: set = set()

            # Build spawn_context so the team lead can spawn workers via
            # the spawn_worker tool.  Only the lead gets this context.
            spawn_context = {
                "team": team,
                "event_queue": event_queue,
                "bedrock": self.bedrock,
                "bus": bus,
                "task_mgr": task_mgr,
            }

            # Start the team lead loop — team_tools_only=True gives it only
            # coordination tools (task_create, send_message, ask_user, spawn_worker, etc.)
            # while workers get the full tool set.  This is structural scoping,
            # like Claude Code giving different subagent_types different tools.
            agent_tasks: List[asyncio.Task] = []
            lead_task = asyncio.create_task(
                run_agent_loop(
                    team=team,
                    agent=team_lead,
                    mailbox=lead_mailbox,
                    bedrock=self.bedrock,
                    message_bus=bus,
                    task_manager=task_mgr,
                    event_queue=event_queue,
                    initial_message=initial_msg,
                    team_tools_only=True,
                    spawn_context=spawn_context,
                )
            )
            agent_tasks.append(lead_task)
            self._register_tasks(team_id, agent_tasks)

            # Signal that agents are now executing (enables Stop button in UI)
            yield SSEEventBuilder.team_task_board(team.team_id, [
                {"title": "Team lead coordinating", "agent": team_lead.name or "team-lead", "status": "executing"}
            ])

            # Drain events from both the message bus SSE queue and the agent event queue.
            # Uses a wall-clock timeout instead of an iteration count so that
            # long-running collaborative sessions aren't killed prematurely.
            shutdown_requested = False
            collab_start = asyncio.get_event_loop().time()
            collab_max_runtime = settings.team_collab_max_runtime  # default 24h
            heartbeat_counter = 0
            # Grace period: require many consecutive idle checks before auto-finishing.
            # The team lead may need time to process completion notifications and
            # create follow-up tasks.  In Claude Code, teams don't auto-finish —
            # only the lead or user ends them.  We use a generous grace period
            # (~30 seconds of all-done + lead-idle) before auto-stopping.
            all_done_idle_checks = 0
            ALL_DONE_GRACE = 30  # ~30 loop iterations (~30 seconds)

            while True:
                if shutdown_requested:
                    break

                # Wall-clock safety limit
                elapsed = asyncio.get_event_loop().time() - collab_start
                if elapsed > collab_max_runtime:
                    logger.warning(
                        f"Collaborative team {team_id} reached max runtime "
                        f"({collab_max_runtime}s), shutting down"
                    )
                    break

                # Check if all agent tasks are done
                all_done = all(t.done() for t in agent_tasks)
                if all_done:
                    # Drain remaining events
                    while not event_queue.empty():
                        event = event_queue.get_nowait()
                        if isinstance(event, str):
                            yield event
                    while True:
                        sse_event = await bus.get_sse_event(timeout=0.5)
                        if sse_event is None:
                            break
                        yield sse_event
                    break

                # Auto-complete: if all tasks on the board are completed and
                # the team lead is idle, count grace iterations before finishing.
                # This gives the user time to send follow-up messages.
                tasks = task_mgr._tasks
                if tasks and all(
                    t.status in ("completed", "error") for t in tasks.values()
                ) and team_lead.status == "idle":
                    all_done_idle_checks += 1
                    if all_done_idle_checks >= ALL_DONE_GRACE:
                        logger.info(
                            f"Collaborative team {team_id}: all tasks completed "
                            f"and team lead idle for {all_done_idle_checks} checks — auto-finishing"
                        )
                        break
                else:
                    all_done_idle_checks = 0

                # Drain agent event queue
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                    if isinstance(event, str):
                        yield event
                    elif isinstance(event, dict):
                        # Internal sentinel events
                        if event.get("__shutdown__"):
                            shutdown_requested = True
                        elif event.get("__spawn_worker__"):
                            # Team lead requested a worker spawn via spawn_worker tool
                            worker_agent = event["worker_agent"]
                            worker_mailbox = event["worker_mailbox"]
                            worker_initial = event["initial_message"]

                            team.agents.append(worker_agent)
                            spawned_workers.add(worker_agent.name)

                            worker_task = asyncio.create_task(
                                run_agent_loop(
                                    team=team,
                                    agent=worker_agent,
                                    mailbox=worker_mailbox,
                                    bedrock=self.bedrock,
                                    message_bus=bus,
                                    task_manager=task_mgr,
                                    event_queue=event_queue,
                                    initial_message=worker_initial,
                                )
                            )
                            agent_tasks.append(worker_task)
                            self._register_tasks(team_id, agent_tasks)

                            # Emit SSE so frontend shows the worker card
                            yield SSEEventBuilder.team_agent_start(
                                team_id=team_id,
                                agent_id=worker_agent.agent_id,
                                role="worker",
                                task_title=worker_agent.role.purpose,
                                agent_name=worker_agent.name,
                            )

                            logger.info(
                                f"Spawned worker '{worker_agent.name}' "
                                f"(requested by team lead)"
                            )
                except asyncio.TimeoutError:
                    pass

                # Drain message bus SSE queue (drain all available, not just one)
                while True:
                    sse_event = await bus.get_sse_event(timeout=0.5)
                    if sse_event is None:
                        break
                    yield sse_event

                # Yield heartbeat every ~10 iterations (~15s) to keep SSE alive
                heartbeat_counter += 1
                if heartbeat_counter % 10 == 0:
                    yield SSEEventBuilder.heartbeat(elapsed)

            # Drain remaining events from both queues before cleanup
            while not event_queue.empty():
                event = event_queue.get_nowait()
                if isinstance(event, str):
                    yield event
            while True:
                sse_event = await bus.get_sse_event(timeout=0.5)
                if sse_event is None:
                    break
                yield sse_event

            # Cleanup agent tasks
            for t in agent_tasks:
                if not t.done():
                    t.cancel()
                    try:
                        await asyncio.wait_for(t, timeout=5.0)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass

            # Emit team_agent_complete for each agent so frontend updates cards
            for agent in team.agents:
                yield SSEEventBuilder.team_agent_complete(
                    team_id=team.team_id,
                    agent_id=agent.agent_id,
                    role=agent.role.name if hasattr(agent.role, 'name') else str(agent.role),
                    task_title="",
                    findings=agent.findings or "",
                    tokens=agent.token_usage,
                )

            # Final result from team lead
            team.status = "complete"
            team.final_result = team_lead.findings or ""
            team.completed_at = datetime.now().isoformat()

            # Calculate total tokens
            for agent in team.agents:
                team.total_tokens["input_tokens"] += agent.token_usage.get("input_tokens", 0)
                team.total_tokens["output_tokens"] += agent.token_usage.get("output_tokens", 0)

            yield SSEEventBuilder.team_complete(
                team.team_id, team.final_result, team.total_tokens
            )
            yield SSEEventBuilder.done()

        except asyncio.CancelledError:
            logger.warning(f"Collaborative team {team.team_id} execution cancelled")
            team.status = "error"
            team.completed_at = datetime.now().isoformat()
            yield SSEEventBuilder.team_error(team.team_id, "Team execution cancelled")
            yield SSEEventBuilder.done()
        except Exception as e:
            logger.error(f"Collaborative team execution error: {e}", exc_info=True)
            team.status = "error"
            yield SSEEventBuilder.team_error(team.team_id, str(e))
            yield SSEEventBuilder.done()
        finally:
            # Clean up message bus, task manager, and task registry
            self._unregister_tasks(team_id)
            from .message_bus import remove_bus
            from .team_task_manager import remove_task_manager
            remove_bus(team_id)
            remove_task_manager(team_id)

    async def stream_team_events(
        self, team_id: str
    ) -> AsyncGenerator[str, None]:
        """Reconnect-safe SSE stream for an already-executing team.

        Drains the message bus SSE queue (collaborative) or the classic event
        queue.  Yields heartbeats to keep the connection alive and terminates
        when the team reaches a terminal status.
        """
        team = self._teams.get(team_id)
        if not team:
            yield SSEEventBuilder.team_error(team_id, "Team not found")
            yield SSEEventBuilder.done()
            return

        from .message_bus import get_bus
        bus = get_bus(team_id)

        # Yield current status snapshot so the reconnecting client catches up
        agent_info = [
            {
                "agent_id": a.agent_id,
                "name": getattr(a, "name", ""),
                "role": a.role.name,
                "purpose": a.role.purpose,
                "status": a.status,
            }
            for a in team.agents
        ]
        yield SSEEventBuilder.team_spawned(team.team_id, agent_info, team.user_request)

        while True:
            # Check if team has reached terminal state
            if team.status in ("complete", "error"):
                if team.status == "complete":
                    yield SSEEventBuilder.team_complete(
                        team.team_id, team.final_result or "", team.total_tokens
                    )
                else:
                    yield SSEEventBuilder.team_error(
                        team.team_id, team.final_result or "Team error"
                    )
                yield SSEEventBuilder.done()
                return

            # Drain message bus SSE events (collaborative mode)
            if bus:
                sse_event = await bus.get_sse_event(timeout=1.0)
                if sse_event:
                    yield sse_event
                    continue  # Drain quickly

            # Heartbeat to keep connection alive
            yield SSEEventBuilder.heartbeat(0)
            await asyncio.sleep(2.0)

    def get_message_bus(self, team_id: str):
        """Get the message bus for a collaborative team."""
        from .message_bus import get_bus
        return get_bus(team_id)

    def get_task_manager_for_team(self, team_id: str):
        """Get the task manager for a collaborative team."""
        from .team_task_manager import get_task_manager as get_tm
        return get_tm(team_id)


# Singleton
_team_manager: Optional[AgentTeamManager] = None


async def _periodic_team_cleanup(manager: AgentTeamManager):
    """Background task that periodically cleans up completed teams."""
    while True:
        try:
            await asyncio.sleep(300)  # Every 5 minutes
            manager.cleanup_completed_teams()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Team cleanup error: {e}")


def get_team_manager() -> AgentTeamManager:
    global _team_manager
    if _team_manager is None:
        _team_manager = AgentTeamManager()
    return _team_manager


async def init_team_manager():
    """Initialize the team manager and start periodic cleanup.

    Call this from the FastAPI lifespan to guarantee the cleanup task runs.
    """
    manager = get_team_manager()
    if manager._cleanup_task is None:
        manager._cleanup_task = asyncio.create_task(
            _periodic_team_cleanup(manager)
        )
        logger.info("Team manager initialized with periodic cleanup task")
    return manager


async def shutdown_team_manager():
    """Cancel the cleanup task and clean up active teams."""
    global _team_manager
    if _team_manager and _team_manager._cleanup_task:
        _team_manager._cleanup_task.cancel()
        try:
            await _team_manager._cleanup_task
        except asyncio.CancelledError:
            pass
        _team_manager._cleanup_task = None
    logger.info("Team manager shut down")
