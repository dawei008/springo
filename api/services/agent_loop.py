"""
Springo Long-Lived Agent Loop
Persistent agent execution model for collaborative team mode.

Each agent runs in a loop:
  receive message -> inject into context -> tool loop -> send response -> idle

The loop reuses the streaming tool execution pattern from agent_team_manager
but adds message handling, team tool interception, and context management.
"""
import json
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from ..models.teams import Team, TeamAgent
from ..utils.streaming import SSEEventBuilder
from ..config import settings
from .message_bus import AgentMailbox, AgentMessage, TeamMessageBus
from .team_task_manager import TeamTaskManager
from .bedrock import BedrockService
from .model_registry import get_model_info, get_model_limits
from .session_state import get_working_dir
from .mcp_manager import get_mcp_manager
from .context_manager import (
    truncate_tool_results, prepare_messages_for_api,
    count_messages_tokens,
)

logger = logging.getLogger(__name__)

# Team tool names that require special handling
TEAM_TOOL_NAMES = {"send_message", "task_create", "task_update", "task_list", "task_get", "ask_user"}


def _get_api_format(model_name: str) -> str:
    info = get_model_info(model_name)
    return info.get("api_format", "anthropic") if info else "anthropic"




def _with_working_dir(system_prompt: str) -> str:
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
        )
    return "".join(parts)


async def run_agent_loop(
    team: Team,
    agent: TeamAgent,
    mailbox: AgentMailbox,
    bedrock: BedrockService,
    message_bus: TeamMessageBus,
    task_manager: TeamTaskManager,
    event_queue: asyncio.Queue,
    initial_message: Optional[AgentMessage] = None,
) -> None:
    """Run a long-lived agent loop.

    The agent processes messages from its mailbox, calls tools as needed,
    and sends responses back through the message bus. It goes idle between
    messages and can be shut down via a shutdown_request message.

    Args:
        team: The team this agent belongs to
        agent: The agent model
        mailbox: The agent's message mailbox
        bedrock: Bedrock service for model calls
        message_bus: The team's message bus
        task_manager: The team's shared task manager
        event_queue: Queue for SSE events
        initial_message: Optional first message to process (skips first receive)
    """
    agent_name = agent.name or agent.agent_id
    model_name = agent.role.model
    model_id = bedrock.get_bedrock_model_id(model_name)
    api_format = _get_api_format(model_name)

    # Build system prompt with team context
    system_base = agent.role.system_prompt
    if agent.custom_instructions and agent.custom_instructions != system_base:
        system_base = agent.custom_instructions + "\n\n" + system_base

    system_prompt = _with_working_dir(
        system_base + _build_team_context_prompt(agent_name, team)
    )

    # Load tools (standard + team tools)
    tools = await _load_team_tools()

    # Conversation history
    messages: List[Dict[str, Any]] = []
    message_count = 0
    consecutive_idle_secs = 0.0
    start_time = asyncio.get_event_loop().time()

    # Limits from config
    max_messages = settings.team_agent_max_messages
    wall_clock_timeout = settings.team_agent_wall_clock_timeout
    idle_timeout = settings.team_idle_timeout

    agent.status = "idle"
    agent.started_at = datetime.now().isoformat()

    logger.info(
        f"[AgentLoop:{agent_name}] Started for team {team.team_id} "
        f"(max_msgs={max_messages}, wall_clock={wall_clock_timeout}s, idle={idle_timeout}s)"
    )

    # Process initial message if provided
    current_message = initial_message

    try:
        while message_count < max_messages:
            # Check wall-clock timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > wall_clock_timeout:
                logger.info(f"[AgentLoop:{agent_name}] Wall-clock timeout ({wall_clock_timeout}s)")
                break

            # Receive next message (or use initial_message on first iteration)
            if current_message is None:
                mailbox.is_idle = True
                agent.status = "idle"
                await message_bus.notify_idle(agent_name)

                current_message = await mailbox.receive(timeout=30.0)
                if current_message is None:
                    # Timeout — send heartbeat and continue waiting
                    consecutive_idle_secs += 30.0
                    if consecutive_idle_secs >= idle_timeout:
                        logger.info(
                            f"[AgentLoop:{agent_name}] Idle timeout ({idle_timeout}s) — self-terminating"
                        )
                        break
                    await event_queue.put(SSEEventBuilder.heartbeat(elapsed))
                    continue

            consecutive_idle_secs = 0.0  # Reset on message received

            mailbox.is_idle = False
            agent.status = "thinking"
            message_count += 1

            # Handle shutdown request
            if current_message.type == "shutdown_request":
                logger.info(f"[AgentLoop:{agent_name}] Received shutdown request")
                await message_bus.notify_shutdown(agent_name)
                agent.status = "complete"
                agent.completed_at = datetime.now().isoformat()
                return

            # Inject message into conversation context
            msg_content = (
                f"[Message from {current_message.sender}]\n"
                f"{current_message.content}"
            )
            messages.append({"role": "user", "content": msg_content})

            # Run tool loop — model responds, potentially calls tools, repeats
            full_text, tokens = await _run_tool_loop(
                agent=agent,
                agent_name=agent_name,
                team=team,
                bedrock=bedrock,
                message_bus=message_bus,
                task_manager=task_manager,
                event_queue=event_queue,
                model_id=model_id,
                model_name=model_name,
                api_format=api_format,
                system_prompt=system_prompt,
                messages=messages,
                tools=tools,
            )

            # Accumulate tokens
            agent.token_usage["input_tokens"] += tokens.get("input_tokens", 0)
            agent.token_usage["output_tokens"] += tokens.get("output_tokens", 0)

            # Store findings
            if full_text:
                agent.findings = full_text

            # Context management: summarize if messages grow too large
            if len(messages) > 30:
                messages = _compact_messages(messages)

            current_message = None  # Go back to receiving

    except asyncio.CancelledError:
        logger.info(f"[AgentLoop:{agent_name}] Cancelled")
    except Exception as e:
        logger.error(f"[AgentLoop:{agent_name}] Error: {e}", exc_info=True)
        agent.status = "error"
        agent.findings = f"Error: {str(e)}"
        await event_queue.put(
            SSEEventBuilder.team_agent_error(
                team.team_id, agent.agent_id, agent.role.name, str(e)
            )
        )
    finally:
        agent.completed_at = datetime.now().isoformat()
        if agent.status not in ("complete", "error"):
            agent.status = "complete"
        logger.info(
            f"[AgentLoop:{agent_name}] Finished. "
            f"Messages processed: {message_count}, "
            f"Tokens: {agent.token_usage}"
        )


async def _run_tool_loop(
    agent: TeamAgent,
    agent_name: str,
    team: Team,
    bedrock: BedrockService,
    message_bus: TeamMessageBus,
    task_manager: TeamTaskManager,
    event_queue: asyncio.Queue,
    model_id: str,
    model_name: str,
    api_format: str,
    system_prompt: str,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
) -> tuple:
    """Run the model tool loop for a single message turn.

    Streams model response, executes tool calls, and iterates until
    the model stops calling tools or hits the iteration limit.

    Returns (full_text, tokens_dict).
    """
    full_text = ""
    _FULL_TEXT_MAX = 100_000  # Cap findings accumulation at ~100K chars
    tokens = {"input_tokens": 0, "output_tokens": 0}
    working_dir = get_working_dir() or None

    agent.status = "executing"

    model_limits = get_model_limits(model_name)

    for iteration in range(1, settings.team_agent_max_tool_iterations + 1):
        # Truncate old tool results to keep context manageable
        if iteration > 1:
            messages = prepare_messages_for_api(messages, keep_recent=3)

        # Emergency truncation if approaching model context limit
        current_tokens = count_messages_tokens(messages)
        max_ctx = model_limits.get("max_context_tokens", 200000)
        if current_tokens > max_ctx * 0.85:
            logger.warning(
                f"[AgentLoop:{agent_name}] Context at {current_tokens:,}/{max_ctx:,} tokens, "
                f"forcing aggressive truncation"
            )
            messages = truncate_tool_results(messages, max_size=2048)

        request_body = {
            "model": model_name,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": messages,
        }
        _, bedrock_body = bedrock.convert_request_to_bedrock(
            request_body,
            include_tools=bool(tools),
            tools=tools if tools else None,
            working_dir=working_dir,
        )

        # Stream response and parse events
        content_blocks = []
        tool_uses = []
        stop_reason = None
        iter_text = ""

        async for event in bedrock.invoke_model_stream(
            model_id, bedrock_body, model_name, api_format=api_format
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
                        if len(full_text) < _FULL_TEXT_MAX:
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

        # No tool calls — done
        if stop_reason != "tool_use" or not tool_uses:
            break

        # Parse accumulated tool inputs
        for tool in tool_uses:
            if "_partial_input" in tool:
                try:
                    tool["input"] = json.loads(tool.pop("_partial_input"))
                except Exception:
                    tool["input"] = {}

        # Execute tools
        mcp_manager = await get_mcp_manager()
        tool_results = []

        for tool in tool_uses:
            tool_name = tool["name"]
            tool_input = tool.get("input", {})

            await event_queue.put(
                SSEEventBuilder.team_agent_tool(
                    team.team_id, agent.agent_id, agent.role.name,
                    tool_name, "start",
                )
            )

            t0 = asyncio.get_event_loop().time()

            # Intercept team tools — inject context and handle async operations
            if tool_name in TEAM_TOOL_NAMES:
                result = await _execute_team_tool(
                    tool_name, tool_input, team.team_id, agent_name,
                    message_bus, task_manager,
                )
                is_error = "error" in result
            else:
                try:
                    result = await asyncio.wait_for(
                        mcp_manager.execute_tool(tool_name, tool_input),
                        timeout=settings.tool_execution_timeout,
                    )
                    is_error = "error" in result
                except asyncio.TimeoutError:
                    result = {"error": f"Tool timed out after {settings.tool_execution_timeout}s"}
                    is_error = True
                except Exception as e:
                    result = {"error": str(e)}
                    is_error = True

            elapsed_tool = asyncio.get_event_loop().time() - t0
            result_str = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)

            logger.info(
                f"[AgentLoop:{agent_name}] Tool {tool_name}: "
                f"{elapsed_tool:.1f}s, error={is_error}"
            )

            await event_queue.put(
                SSEEventBuilder.team_agent_tool(
                    team.team_id, agent.agent_id, agent.role.name,
                    tool_name, "error" if is_error else "complete",
                    result_str[:200],
                )
            )

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool["id"],
                "content": result_str[:8000],
                "is_error": is_error,
            })

        # Append assistant + tool results for next iteration
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

    return full_text, tokens


async def _execute_team_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    team_id: str,
    agent_name: str,
    message_bus: TeamMessageBus,
    task_manager: TeamTaskManager,
) -> Dict[str, Any]:
    """Execute a team communication tool with injected context.

    Handles the async delivery of messages and task updates
    that can't be done in the sync tool handler.
    """
    if tool_name == "send_message":
        msg_type = tool_input.get("type", "message")
        recipient = tool_input.get("recipient", "")
        content = tool_input.get("content", "")
        summary = tool_input.get("summary", content[:50] if content else "")

        if not content:
            return {"error": "content is required"}
        if msg_type == "message" and not recipient:
            return {"error": "recipient is required for direct messages"}

        msg = AgentMessage(
            type=msg_type,
            sender=agent_name,
            recipient=recipient,
            content=content,
            summary=summary,
        )

        if msg_type == "broadcast":
            await message_bus.broadcast(msg)
        elif msg_type == "shutdown_request":
            msg.type = "shutdown_request"
            await message_bus.send_message(msg)
        else:
            await message_bus.send_message(msg)

        return {
            "status": "sent",
            "type": msg_type,
            "sender": agent_name,
            "recipient": recipient if msg_type != "broadcast" else "all",
            "message_id": msg.message_id,
        }

    elif tool_name == "task_create":
        subject = tool_input.get("subject", "")
        description = tool_input.get("description", "")
        active_form = tool_input.get("active_form", "")

        if not subject:
            return {"error": "subject is required"}

        task = await task_manager.create_task_async(
            subject=subject,
            description=description,
            active_form=active_form,
        )
        return {
            "status": "created",
            "task_id": task.task_id,
            "title": task.title,
        }

    elif tool_name == "task_update":
        task_id = tool_input.get("task_id", "")
        if not task_id:
            return {"error": "task_id is required"}

        task = await task_manager.update_task(
            task_id=task_id,
            status=tool_input.get("status"),
            subject=tool_input.get("subject"),
            description=tool_input.get("description"),
            active_form=tool_input.get("active_form"),
            owner=tool_input.get("owner"),
            add_blocks=tool_input.get("add_blocks"),
            add_blocked_by=tool_input.get("add_blocked_by"),
        )
        if not task:
            return {"error": f"Task {task_id} not found"}
        return {
            "status": "updated",
            "task_id": task.task_id,
            "task_status": task.status,
            "owner": task.owner,
        }

    elif tool_name == "task_list":
        tasks = task_manager.list_tasks()
        return {
            "tasks": [
                {
                    "task_id": t.task_id,
                    "title": t.title,
                    "status": t.status,
                    "owner": t.owner,
                    "blocked_by": [
                        bid for bid in t.blocked_by
                        if task_manager.get_task(bid) and task_manager.get_task(bid).status != "completed"
                    ],
                }
                for t in tasks
            ],
        }

    elif tool_name == "task_get":
        task_id = tool_input.get("task_id", "")
        if not task_id:
            return {"error": "task_id is required"}

        task = task_manager.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        return {
            "task_id": task.task_id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "owner": task.owner,
            "active_form": task.active_form,
            "blocks": task.blocks,
            "blocked_by": task.blocked_by,
        }

    elif tool_name == "ask_user":
        question = tool_input.get("question", "")
        options = tool_input.get("options", [])
        if not question:
            return {"error": "question is required"}

        is_team_lead = agent_name == "team-lead"

        if is_team_lead:
            # Team lead asks the user directly via SSE
            options_text = ""
            if options:
                options_text = "\n".join(
                    f"  {i+1}. {o.get('label', '')} — {o.get('description', '')}"
                    for i, o in enumerate(options)
                )

            display_content = question
            if options_text:
                display_content += "\n\nOptions:\n" + options_text

            # Emit SSE event for the frontend question UI
            sse_event = SSEEventBuilder.team_ask_user(
                team_id=team_id,
                agent_name=agent_name,
                question=question,
                options=options,
            )
            await message_bus.emit_sse(sse_event)

            # Also emit as a message event so it appears in team messages panel
            msg = AgentMessage(
                type="message",
                sender=agent_name,
                recipient="user",
                content=display_content,
                summary=f"Question: {question[:40]}",
            )
            sse_msg_event = SSEEventBuilder.team_agent_message(
                team_id=team_id,
                sender=agent_name,
                recipient="user",
                content=display_content,
                summary=f"Question: {question[:40]}",
                message_id=msg.message_id,
            )
            await message_bus.emit_sse(sse_msg_event)

            return {
                "status": "question_sent",
                "message": (
                    "Question sent to the user. They will respond via the team message input. "
                    "Wait for their reply — it will arrive as your next message."
                ),
            }
        else:
            # Worker cannot ask user directly — route through team lead
            relay_content = (
                f"[Clarification needed from user]\n"
                f"Worker '{agent_name}' needs to ask the user:\n\n"
                f"{question}"
            )
            if options:
                relay_content += "\n\nSuggested options:\n" + "\n".join(
                    f"  - {o.get('label', '')}: {o.get('description', '')}"
                    for o in options
                )
            relay_content += (
                "\n\nPlease use ask_user to ask the user this question, "
                "then forward their answer back to me."
            )

            msg = AgentMessage(
                type="message",
                sender=agent_name,
                recipient="team-lead",
                content=relay_content,
                summary=f"Needs user input: {question[:30]}",
            )
            await message_bus.send_message(msg)

            return {
                "status": "forwarded_to_team_lead",
                "message": (
                    "You cannot ask the user directly. Your question has been sent to the team lead. "
                    "The team lead will ask the user and forward their response to you. "
                    "Wait for the team lead's reply — it will arrive as your next message."
                ),
            }

    return {"error": f"Unknown team tool: {tool_name}"}


async def _load_team_tools() -> List[Dict[str, Any]]:
    """Load standard MCP tools plus team communication tools."""
    tools = []
    try:
        mcp_mgr = await get_mcp_manager()
        tool_defs = mcp_mgr.get_tool_definitions()
        if tool_defs:
            tools = [t.model_dump() if hasattr(t, "model_dump") else t for t in tool_defs]
    except Exception as e:
        logger.warning(f"Failed to load tools: {e}")

    # Add team tool schemas
    from mcp_tools.schemas_team import TEAM_TOOL_DEFINITIONS
    import copy
    tools.extend(copy.deepcopy(TEAM_TOOL_DEFINITIONS))

    return tools


def _build_team_context_prompt(agent_name: str, team: Team) -> str:
    """Build additional system prompt with team context information."""
    other_agents = [a for a in team.agents if a.name != agent_name]
    agent_list = ", ".join(a.name or a.agent_id for a in other_agents) if other_agents else "none yet"
    is_lead = agent_name == "team-lead"

    base = (
        f"\n\n## Team Context\n"
        f"You are agent '{agent_name}' in team '{team.team_id}'.\n"
        f"Team request: {team.user_request}\n"
        f"Other agents: {agent_list}\n\n"
        f"You have access to team tools:\n"
        f"- send_message: Send DMs to teammates or broadcast to all\n"
        f"- task_create: Create tasks on the shared task board\n"
        f"- task_update: Update task status, assign owners, set dependencies\n"
        f"- task_list: List all tasks\n"
        f"- task_get: Get full task details\n"
        f"- ask_user: Ask the user a question for clarification\n\n"
    )

    if is_lead:
        base += (
            f"As team lead, you can ask the user questions directly using ask_user. "
            f"If a worker sends you a clarification request, use ask_user to relay it to the user, "
            f"then forward the user's answer back to that worker via send_message.\n\n"
            f"Coordinate with your team using these tools. When you finish processing a message, "
            f"provide your response and then wait for the next message.\n"
        )
    else:
        base += (
            f"IMPORTANT: You cannot ask the user directly. If you need clarification from the user, "
            f"call ask_user — it will automatically route your question to the team lead, "
            f"who will ask the user and forward the answer to you.\n\n"
            f"Focus on completing your assigned tasks. When you finish processing a message, "
            f"provide your response and then wait for the next message.\n"
        )

    return base


def _compact_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Summarize old messages to manage context window growth.

    Keeps the first message (initial context) and the last 10 messages,
    replacing the middle with a summary.
    """
    if len(messages) <= 12:
        return messages

    # Keep first message and last 10
    first = messages[:1]
    last = messages[-10:]

    # Summarize the middle
    middle_count = len(messages) - 11
    summary = {
        "role": "user",
        "content": (
            f"[Context compacted: {middle_count} earlier messages were summarized. "
            f"The conversation started with the initial task assignment. "
            f"You have been working with your team and processing messages.]"
        ),
    }

    return first + [summary] + last
