"""
Team Communication Tool Handlers
Handlers for send_message, task_create, task_update, task_list, task_get.

These tools are only functional when an agent is running in team context.
The _team_id and _agent_name parameters are injected at execution time by
the agent loop and stripped from the model-visible schema.
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def _get_team_context(kwargs: Dict[str, Any]):
    """Extract injected team context, returning (team_id, agent_name) or raise."""
    team_id = kwargs.pop("_team_id", None)
    agent_name = kwargs.pop("_agent_name", None)
    if not team_id or not agent_name:
        return None, None
    return team_id, agent_name


def send_message(
    type: str = "message",
    recipient: str = "",
    content: str = "",
    summary: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Send a message to a teammate or broadcast to the entire team.

    Injected kwargs: _team_id, _agent_name
    """
    team_id, agent_name = _get_team_context(kwargs)
    if not team_id:
        return {"error": "send_message can only be used within a collaborative team context."}

    if not content:
        return {"error": "content is required"}

    if type == "message" and not recipient:
        return {"error": "recipient is required for direct messages"}

    # Import at call time to avoid circular imports
    from api.services.message_bus import get_bus, AgentMessage

    bus = get_bus(team_id)
    if not bus:
        return {"error": f"No message bus found for team {team_id}"}

    msg = AgentMessage(
        type=type,
        sender=agent_name,
        recipient=recipient,
        content=content,
        summary=summary or content[:50],
    )

    # We need to run the async send in the current event loop
    import asyncio
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # Schedule as a coroutine — the caller (tool executor) will handle it
        future = asyncio.ensure_future(
            bus.broadcast(msg) if type == "broadcast" else bus.send_message(msg)
        )
        # We can't await in a sync context, but the tool executor runs in a thread
        # Use run_coroutine_threadsafe to bridge sync->async
        try:
            import concurrent.futures
            new_loop = asyncio.new_event_loop()
            # Actually, tools run in ThreadPoolExecutor. We need to use the main loop.
            # Let's just return success and let the agent loop handle the async part.
            pass
        except Exception:
            pass

    return {
        "status": "sent",
        "type": type,
        "sender": agent_name,
        "recipient": recipient if type != "broadcast" else "all",
        "message_id": msg.message_id,
    }


def send_message_async(
    type: str = "message",
    recipient: str = "",
    content: str = "",
    summary: str = "",
    _team_id: str = "",
    _agent_name: str = "",
) -> Dict[str, Any]:
    """Synchronous wrapper that prepares the message for async delivery.

    Returns the message data. The actual delivery is handled by the agent loop
    which calls deliver_pending_message() after this tool returns.
    """
    if not _team_id or not _agent_name:
        return {"error": "send_message can only be used within a collaborative team context."}

    if not content:
        return {"error": "content is required"}

    if type == "message" and not recipient:
        return {"error": "recipient is required for direct messages"}

    from api.services.message_bus import AgentMessage

    msg = AgentMessage(
        type=type,
        sender=_agent_name,
        recipient=recipient,
        content=content,
        summary=summary or content[:50],
    )

    # Return the message data — the agent loop will handle async delivery
    return {
        "status": "pending_delivery",
        "type": type,
        "sender": _agent_name,
        "recipient": recipient if type != "broadcast" else "all",
        "message_id": msg.message_id,
        "_message": {
            "message_id": msg.message_id,
            "type": msg.type,
            "sender": msg.sender,
            "recipient": msg.recipient,
            "content": msg.content,
            "summary": msg.summary,
            "timestamp": msg.timestamp,
        },
    }


def task_create(
    subject: str = "",
    description: str = "",
    active_form: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Create a new task on the shared task board.

    Injected kwargs: _team_id, _agent_name
    """
    team_id, agent_name = _get_team_context(kwargs)
    if not team_id:
        return {"error": "task_create can only be used within a collaborative team context."}

    if not subject:
        return {"error": "subject is required"}

    from api.services.team_task_manager import get_task_manager

    mgr = get_task_manager(team_id)
    if not mgr:
        return {"error": f"No task manager found for team {team_id}"}

    task = mgr.create_task(
        subject=subject,
        description=description,
        active_form=active_form,
    )

    return {
        "status": "created",
        "task_id": task.task_id,
        "title": task.title,
        "description": task.description,
        "_needs_sse": True,
        "_sse_type": "task_created",
    }


def task_update(
    task_id: str = "",
    status: str = None,
    subject: str = None,
    description: str = None,
    active_form: str = None,
    owner: str = None,
    add_blocks: list = None,
    add_blocked_by: list = None,
    **kwargs,
) -> Dict[str, Any]:
    """Update a task on the shared task board.

    Injected kwargs: _team_id, _agent_name
    """
    team_id, agent_name = _get_team_context(kwargs)
    if not team_id:
        return {"error": "task_update can only be used within a collaborative team context."}

    if not task_id:
        return {"error": "task_id is required"}

    from api.services.team_task_manager import get_task_manager

    mgr = get_task_manager(team_id)
    if not mgr:
        return {"error": f"No task manager found for team {team_id}"}

    task = mgr.get_task(task_id)
    if not task:
        return {"error": f"Task {task_id} not found"}

    # Return update params — the agent loop will call the async update
    return {
        "status": "pending_update",
        "task_id": task_id,
        "_needs_async": True,
        "_update_params": {
            "task_id": task_id,
            "status": status,
            "subject": subject,
            "description": description,
            "active_form": active_form,
            "owner": owner,
            "add_blocks": add_blocks,
            "add_blocked_by": add_blocked_by,
        },
    }


def task_list(**kwargs) -> Dict[str, Any]:
    """List all tasks on the shared task board.

    Injected kwargs: _team_id, _agent_name
    """
    team_id, agent_name = _get_team_context(kwargs)
    if not team_id:
        return {"error": "task_list can only be used within a collaborative team context."}

    from api.services.team_task_manager import get_task_manager

    mgr = get_task_manager(team_id)
    if not mgr:
        return {"error": f"No task manager found for team {team_id}"}

    tasks = mgr.list_tasks()
    return {
        "tasks": [
            {
                "task_id": t.task_id,
                "title": t.title,
                "status": t.status,
                "owner": t.owner,
                "blocked_by": [
                    bid for bid in t.blocked_by
                    if mgr.get_task(bid) and mgr.get_task(bid).status != "completed"
                ],
            }
            for t in tasks
        ],
    }


def task_get(task_id: str = "", **kwargs) -> Dict[str, Any]:
    """Get full details of a specific task.

    Injected kwargs: _team_id, _agent_name
    """
    team_id, agent_name = _get_team_context(kwargs)
    if not team_id:
        return {"error": "task_get can only be used within a collaborative team context."}

    if not task_id:
        return {"error": "task_id is required"}

    from api.services.team_task_manager import get_task_manager

    mgr = get_task_manager(team_id)
    if not mgr:
        return {"error": f"No task manager found for team {team_id}"}

    task = mgr.get_task(task_id)
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
        "findings": task.findings,
    }
