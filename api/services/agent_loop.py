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
    count_messages_tokens, repair_orphan_tool_uses,
)

logger = logging.getLogger(__name__)

# Team tool names that require special handling
TEAM_TOOL_NAMES = {"send_message", "task_create", "task_update", "task_list", "task_get", "ask_user", "spawn_worker", "exit_plan_mode", "team_info"}


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


def _load_team_only_tools() -> List[Dict[str, Any]]:
    """Load only team coordination tools (no MCP/execution tools).

    Used for the team lead agent, which delegates all execution work
    to workers and only needs coordination tools.  This is a structural
    constraint — like Claude Code giving different subagent_types
    different tool sets.
    """
    from mcp_tools.schemas_team import TEAM_TOOL_DEFINITIONS
    import copy
    return copy.deepcopy(TEAM_TOOL_DEFINITIONS)


async def run_agent_loop(
    team: Team,
    agent: TeamAgent,
    mailbox: AgentMailbox,
    bedrock: BedrockService,
    message_bus: TeamMessageBus,
    task_manager: TeamTaskManager,
    event_queue: asyncio.Queue,
    initial_message: Optional[AgentMessage] = None,
    team_tools_only: bool = False,
    spawn_context: Optional[Dict[str, Any]] = None,
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
        spawn_context: Optional dict with team/event_queue/bedrock for spawn_worker
                       (only provided to the team lead)
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

    # Load tools — team lead gets only team tools (structural scoping),
    # workers get all tools (MCP + team tools).
    if team_tools_only:
        tools = _load_team_only_tools()
    else:
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

            # Handle shutdown request — inject as message so the model can approve/reject
            if current_message.type == "shutdown_request":
                logger.info(f"[AgentLoop:{agent_name}] Received shutdown request from {current_message.sender}")
                msg_content = (
                    f"[Shutdown Request from {current_message.sender}]\n"
                    f"{current_message.content}\n\n"
                    f"You have received a shutdown request (request_id: {current_message.message_id}). "
                    f"To approve, call send_message with type='shutdown_response', "
                    f"approve=true, request_id='{current_message.message_id}', "
                    f"and content describing your status. "
                    f"To reject, set approve=false with a reason."
                )
                messages.append({"role": "user", "content": msg_content})
            else:
                # Inject message into conversation context
                msg_content = (
                    f"[Message from {current_message.sender}]\n"
                    f"{current_message.content}"
                )
                messages.append({"role": "user", "content": msg_content})

            # Run tool loop — model responds, potentially calls tools, repeats
            full_text, tokens, messages = await _run_tool_loop(
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
                spawn_context=spawn_context,
            )

            # Accumulate tokens
            agent.token_usage["input_tokens"] += tokens.get("input_tokens", 0)
            agent.token_usage["output_tokens"] += tokens.get("output_tokens", 0)

            # Store findings
            if full_text:
                agent.findings = full_text

            # Check if agent approved shutdown during this tool loop
            if mailbox.shutdown_approved:
                logger.info(f"[AgentLoop:{agent_name}] Shutdown approved — terminating")
                await message_bus.notify_shutdown(agent_name)
                agent.status = "complete"
                agent.completed_at = datetime.now().isoformat()
                return

            # Context management: summarize if messages grow too large
            if len(messages) > 30:
                messages = _compact_messages(messages)
                messages = repair_orphan_tool_uses(messages)

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
    spawn_context: Optional[Dict[str, Any]] = None,
) -> tuple:
    """Run the model tool loop for a single message turn.

    Streams model response, executes tool calls, and iterates until
    the model stops calling tools or hits the iteration limit.

    Returns (full_text, tokens_dict, messages).
    """
    full_text = ""
    _FULL_TEXT_MAX = 100_000  # Cap findings accumulation at ~100K chars
    tokens = {"input_tokens": 0, "output_tokens": 0}
    working_dir = get_working_dir() or None
    consecutive_poll_only = 0  # Anti-polling: track consecutive task_list-only iterations
    _POLL_TOOLS = {"task_list"}  # Only task_list is polling; task_get is reviewing details

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

        # Repair orphaned tool_use/tool_result pairs after any truncation
        messages = repair_orphan_tool_uses(messages)

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
                block_index = data.get("index", len(content_blocks))
                if block.get("type") == "tool_use":
                    entry = {
                        "type": "tool_use",
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "input": {},
                        "_block_index": block_index,
                    }
                    content_blocks.append(entry)
                    tool_uses.append(entry)
                elif block.get("type") == "text":
                    content_blocks.append({"type": "text", "text": "", "_block_index": block_index})

            elif evt_type == "content_block_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "input_json_delta" and tool_uses:
                    partial = delta.get("partial_json", "")
                    if partial:
                        # Route delta to the correct tool_use by matching block index
                        delta_index = data.get("index")
                        target = tool_uses[-1]  # fallback to last
                        if delta_index is not None:
                            for tu in tool_uses:
                                if tu.get("_block_index") == delta_index:
                                    target = tu
                                    break
                        target["_partial_input"] = (
                            target.get("_partial_input", "") + partial
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
            tool.pop("_block_index", None)  # clean up internal tracking field
            if "_partial_input" in tool:
                raw = tool.pop("_partial_input")
                try:
                    tool["input"] = json.loads(raw)
                except Exception as e:
                    logger.warning(f"[AgentLoop:{agent_name}] Failed to parse tool input JSON for {tool.get('name')}: {e}, raw={raw[:200]}")
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
                    spawn_context=spawn_context,
                    team=team,
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

        # Anti-polling: detect consecutive iterations where the model only
        # calls read-only status tools (task_list, task_get).  This is the
        # team lead stuck in a polling loop waiting for workers.  After 2
        # consecutive poll-only iterations, break so it goes idle and waits
        # for worker messages — matching Claude Code's idle-between-turns
        # pattern.
        tool_names_this_iter = {t["name"] for t in tool_uses}
        if tool_names_this_iter and tool_names_this_iter <= _POLL_TOOLS:
            consecutive_poll_only += 1
            if consecutive_poll_only >= 3:
                logger.info(
                    f"[AgentLoop:{agent_name}] Detected polling loop "
                    f"({consecutive_poll_only} consecutive status-only iterations), "
                    f"yielding control"
                )
                break
        else:
            consecutive_poll_only = 0

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

    return full_text, tokens, messages


async def _execute_team_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    team_id: str,
    agent_name: str,
    message_bus: TeamMessageBus,
    task_manager: TeamTaskManager,
    spawn_context: Optional[Dict[str, Any]] = None,
    team: Optional[Team] = None,
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
            logger.warning(
                f"[{agent_name}] send_message missing content, "
                f"input keys={list(tool_input.keys())}, input={str(tool_input)[:200]}"
            )
            return {"error": "content is required"}
        if msg_type == "message" and not recipient:
            logger.warning(
                f"[{agent_name}] send_message missing recipient, "
                f"type={msg_type}, input keys={list(tool_input.keys())}, input={str(tool_input)[:200]}"
            )
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
        elif msg_type == "shutdown_response":
            approve = tool_input.get("approve", False)
            request_id = tool_input.get("request_id", "")
            if approve:
                # Mark this agent's mailbox for shutdown after tool loop returns
                agent_mailbox = message_bus.get_mailbox(agent_name)
                if agent_mailbox:
                    agent_mailbox.shutdown_approved = True
            # Deliver the response to the requester
            response_content = (
                f"[Shutdown {'Approved' if approve else 'Rejected'}] "
                f"{content}"
            )
            response_msg = AgentMessage(
                type="message",
                sender=agent_name,
                recipient=recipient,
                content=response_content,
                summary=f"Shutdown {'approved' if approve else 'rejected'}",
            )
            await message_bus.send_message(response_msg)
        elif msg_type == "plan_approval_response":
            approve = tool_input.get("approve", False)
            if not recipient:
                return {"error": "recipient is required for plan_approval_response"}
            prefix = "[Plan Approved]" if approve else "[Plan Rejected]"
            approval_msg = AgentMessage(
                type="message",
                sender=agent_name,
                recipient=recipient,
                content=f"{prefix} {content}",
                summary=f"Plan {'approved' if approve else 'rejected'}",
            )
            await message_bus.send_message(approval_msg)
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
        # Accept 'title' as fallback for 'subject' (some models use different field names)
        subject = tool_input.get("subject", "") or tool_input.get("title", "") or tool_input.get("name", "")
        description = tool_input.get("description", "") or tool_input.get("content", "")
        active_form = tool_input.get("active_form", "") or tool_input.get("activeForm", "")

        if not subject:
            logger.warning(f"task_create missing subject, received keys: {list(tool_input.keys())}, input: {str(tool_input)[:200]}")
            return {"error": f"subject is required. Received fields: {list(tool_input.keys())}. Use 'subject' for the task title."}

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

        # Guard: only the task owner can mark a task as "completed".
        # The team lead should not mark other agents' in-progress tasks
        # as completed — only the worker doing the work knows when it's done.
        new_status = tool_input.get("status")
        if new_status == "completed":
            existing = task_manager.get_task(task_id)
            if existing and existing.owner and existing.owner != agent_name:
                return {
                    "error": (
                        f"Only the task owner ('{existing.owner}') can mark task "
                        f"#{task_id} as completed. If the task is no longer needed, "
                        f"use status='error' or send a message to the owner."
                    ),
                }

        task = await task_manager.update_task(
            task_id=task_id,
            status=new_status,
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
        result = {
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
        # Hint the team lead to stop polling and wait for worker messages
        in_progress = [t for t in tasks if t.status == "in_progress"]
        if in_progress and agent_name == "team-lead":
            result["note"] = (
                f"{len(in_progress)} task(s) still in progress. "
                "Workers will send you a message when they finish. "
                "Stop and wait for incoming messages instead of polling task_list."
            )
        return result

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

    elif tool_name == "spawn_worker":
        if not spawn_context:
            return {"error": "spawn_worker is only available to the team lead"}

        worker_name = tool_input.get("name", "")
        task_ids = tool_input.get("task_ids", [])

        if not worker_name:
            return {"error": "name is required"}
        if not task_ids:
            return {"error": "task_ids is required (provide at least one task ID)"}
        if worker_name == "team-lead":
            return {"error": "Cannot use 'team-lead' as worker name"}

        # Check if worker name is already taken
        team = spawn_context["team"]
        for existing_agent in team.agents:
            if existing_agent.name == worker_name:
                return {"error": f"Worker name '{worker_name}' is already in use"}

        # Validate all task IDs exist
        for tid in task_ids:
            task = task_manager.get_task(tid)
            if not task:
                return {"error": f"Task '{tid}' not found"}

        # Gather task descriptions for the initial message
        # (all task_ids validated above, so get_task won't return None)
        task_descriptions = []
        task_titles = []
        for tid in task_ids:
            t = task_manager.get_task(tid)
            if t:  # guaranteed by validation above
                task_descriptions.append(
                    f"**Task #{t.task_id}**: {t.title}\n{t.description}"
                )
                task_titles.append(t.title)

        # Build initial message with all assigned tasks
        initial_content = (
            f"You are assigned the following task(s):\n\n"
            + "\n\n".join(task_descriptions)
            + "\n\nPlease complete "
            + ("this task" if len(task_ids) == 1 else "these tasks")
            + ". When done, call task_update with status='completed' for each task, "
            "then send a brief summary to team-lead with send_message.\n"
            "If you need to ask the user anything, use ask_user."
        )

        # Create worker agent and role
        plan_mode = tool_input.get("plan_mode", False)
        from ..models.teams import TeamAgent as _TeamAgent, AgentRole as _AgentRole

        base_system_prompt = (
            "You are a worker agent. Complete the task(s) assigned to you thoroughly.\n"
            "When done:\n"
            "1. Use task_update to mark each task as completed.\n"
            "2. Use send_message to send a brief summary of your findings to team-lead.\n"
            "If you need clarification from the user, use ask_user.\n"
            "Do NOT use emojis in any output or messages."
        )
        if plan_mode:
            base_system_prompt = (
                "You are a worker agent in PLAN MODE.\n\n"
                "Before implementing anything, you MUST:\n"
                "1. Analyze the task requirements thoroughly\n"
                "2. Create a detailed implementation plan\n"
                "3. Call exit_plan_mode with your plan\n"
                "4. Wait for the team lead's approval (you will receive a message "
                "with [Plan Approved] or [Plan Rejected])\n"
                "5. Only after receiving [Plan Approved], proceed with implementation\n\n"
                "If your plan is rejected, revise based on the feedback and resubmit.\n\n"
                "After implementation is complete:\n"
                "1. Use task_update to mark each task as completed.\n"
                "2. Use send_message to send a brief summary of your findings to team-lead.\n"
                "If you need clarification from the user, use ask_user.\n"
                "Do NOT use emojis in any output or messages."
            )

        worker_role = _AgentRole(
            name="worker",
            system_prompt=base_system_prompt,
            model=team.agents[0].role.model,  # Use team lead's model
            purpose=", ".join(task_titles),
        )
        worker_agent = _TeamAgent(
            name=worker_name,
            role=worker_role,
        )

        # Register mailbox
        bus = spawn_context["bus"]
        worker_mailbox = bus.register_agent(worker_name)

        # Claim the tasks
        for tid in task_ids:
            await task_manager.update_task(tid, status="in_progress", owner=worker_name)

        # Build initial message
        worker_initial = AgentMessage(
            type="message",
            sender="team-lead",
            recipient=worker_name,
            content=initial_content,
            summary=f"Task assignment: {task_descriptions[0][:40]}",
        )

        # Put spawn sentinel on event queue for the main loop to handle
        event_queue = spawn_context["event_queue"]
        await event_queue.put({
            "__spawn_worker__": True,
            "worker_agent": worker_agent,
            "worker_mailbox": worker_mailbox,
            "initial_message": worker_initial,
        })

        return {
            "status": "spawned",
            "worker_name": worker_name,
            "task_ids": task_ids,
            "message": (
                f"Worker '{worker_name}' is being spawned and will start working on "
                f"{len(task_ids)} task(s) immediately. The worker will message you "
                "when tasks are completed."
            ),
        }

    elif tool_name == "exit_plan_mode":
        plan = tool_input.get("plan", "")
        if not plan:
            return {"error": "plan is required"}

        # Send plan to team-lead for approval
        plan_msg = AgentMessage(
            type="message",
            sender=agent_name,
            recipient="team-lead",
            content=(
                f"[Plan Approval Request]\n"
                f"Worker '{agent_name}' has submitted an implementation plan for review:\n\n"
                f"{plan}\n\n"
                f"To approve, call send_message with type='plan_approval_response', "
                f"recipient='{agent_name}', approve=true, and content='Approved'.\n"
                f"To reject, set approve=false with feedback in content."
            ),
            summary=f"Plan from {agent_name}",
        )
        await message_bus.send_message(plan_msg)

        return {
            "status": "plan_submitted",
            "message": (
                "Your plan has been sent to the team lead for review. "
                "Wait for their approval before proceeding with implementation. "
                "You will receive a message with [Plan Approved] or [Plan Rejected]."
            ),
        }

    elif tool_name == "team_info":
        if not team:
            return {"error": "team context not available"}

        members = []
        for a in team.agents:
            members.append({
                "name": a.name or a.agent_id,
                "agent_id": a.agent_id,
                "role": a.role.name if a.role else "unknown",
                "status": a.status or "unknown",
                "purpose": a.role.purpose if a.role and a.role.purpose else "",
            })

        return {
            "team_id": team.team_id,
            "status": team.status,
            "user_request": team.user_request,
            "members": members,
        }

    return {"error": f"Unknown team tool: {tool_name}"}


async def _load_team_tools() -> List[Dict[str, Any]]:
    """Load standard MCP tools plus team communication tools (for workers).

    Workers get all MCP tools plus team tools, but NOT spawn_worker
    (only the team lead can spawn workers).  Also deduplicates by tool name
    to avoid Bedrock's "Tool names must be unique" validation error.
    """
    tools = []
    seen_names: set = set()
    try:
        mcp_mgr = await get_mcp_manager()
        tool_defs = mcp_mgr.get_tool_definitions()
        if tool_defs:
            for t in tool_defs:
                td = t.model_dump() if hasattr(t, "model_dump") else t
                name = td.get("name", "")
                if name and name not in seen_names:
                    tools.append(td)
                    seen_names.add(name)
    except Exception as e:
        logger.warning(f"Failed to load tools: {e}")

    # Add team tool schemas (excluding spawn_worker — that's team-lead only)
    from mcp_tools.schemas_team import TEAM_TOOL_DEFINITIONS
    import copy
    for td in TEAM_TOOL_DEFINITIONS:
        if td["name"] == "spawn_worker":
            continue  # Only available to team lead via _load_team_only_tools
        if td["name"] not in seen_names:
            tools.append(copy.deepcopy(td))
            seen_names.add(td["name"])

    return tools


def _build_team_context_prompt(agent_name: str, team: Team) -> str:
    """Build additional system prompt with team context information.

    Uses descriptive style (like Claude Code's team prompts) rather than
    prescriptive tool restrictions.  Behavior is guided by role description
    and structural tool scoping, not "NEVER use X" rules.
    """
    other_agents = [a for a in team.agents if a.name != agent_name]
    agent_list = ", ".join(a.name or a.agent_id for a in other_agents) if other_agents else "none yet"
    is_lead = agent_name == "team-lead"

    base = (
        f"\n\n## Team Context\n"
        f"You are '{agent_name}' in team '{team.team_id}'.\n"
        f"Team request: {team.user_request}\n"
        f"Other agents: {agent_list}\n\n"
    )

    if is_lead:
        base += (
            "## Worker Clarification Relay\n"
            "When a worker sends you a message requesting user input:\n"
            "1. Call ask_user with the worker's question\n"
            "2. Wait for the user's reply (arrives as your next message)\n"
            "3. Forward the user's answer to that worker using send_message\n"
            "Always relay — do not answer on behalf of the user.\n"
        )
    else:
        base += (
            "If you need user input or clarification, call ask_user — it routes "
            "through the team lead who relays the answer back. After calling "
            "ask_user, wait for the reply before proceeding.\n\n"
            "When you finish your task:\n"
            "1. Mark it completed with task_update\n"
            "2. Send a brief summary to team-lead with send_message\n"
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

    # Summarize the middle as a user+assistant pair to maintain alternation
    middle_count = len(messages) - 11
    summary_user = {
        "role": "user",
        "content": (
            f"[Context compacted: {middle_count} earlier messages were summarized. "
            f"The conversation started with the initial task assignment. "
            f"You have been working with your team and processing messages.]"
        ),
    }
    summary_ack = {
        "role": "assistant",
        "content": "Understood. I have the context from earlier messages. Continuing.",
    }

    return first + [summary_user, summary_ack] + last
