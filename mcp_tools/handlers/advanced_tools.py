"""
Advanced Agent Tools
Background tasks and cross-session delegation
"""

import uuid
import time
from typing import Any, Dict

from ..session import get_session_state, add_background_agent


def task(description: str, prompt: str, agent_type: str = "general", run_in_background: bool = True) -> Dict[str, Any]:
    """
    Launch a background task in a new session.
    The task will execute asynchronously and results will be returned to the main session.

    Args:
        description: Short description of the task (3-5 words)
        prompt: Detailed instructions for the task
        agent_type: Type of agent (explore, research, implement, general)
        run_in_background: Whether to run in background (default: True)

    Returns:
        A dict with ui_action: "launch_background_task" for frontend handling
    """
    task_id = f"task_{uuid.uuid4().hex[:8]}"

    # Agent type configurations
    AGENT_CONFIGS = {
        "explore": {"name": "Code Explorer", "description": "Specialized for exploring and understanding code"},
        "research": {"name": "Researcher", "description": "Specialized for web research and information gathering"},
        "implement": {"name": "Code Implementer", "description": "Specialized for implementing code changes"},
        "general": {"name": "General Agent", "description": "General purpose agent with access to all tools"}
    }

    if agent_type not in AGENT_CONFIGS:
        return {"error": f"Unknown agent type: {agent_type}. Available: {list(AGENT_CONFIGS.keys())}"}

    config = AGENT_CONFIGS[agent_type]

    # Return a structure that triggers background task execution in a new session
    return {
        "success": True,
        "task_id": task_id,
        "type": "background_task",
        "ui_action": "launch_background_task",
        "description": description,
        "prompt": prompt,
        "agent_type": agent_type,
        "agent_name": config["name"],
        "create_new_session": True,
        "session_name": f"Task: {description[:30]}...",
        "message": f"Launching background task: {description}"
    }


def delegate_task(task_description: str, target_session: str = None,
                  priority: str = "normal", context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Delegate a task to another session or create a new delegation.

    This enables cross-session task management where one conversation
    can delegate work to be picked up by another.
    """
    delegation_id = f"delegation_{uuid.uuid4().hex[:8]}"

    delegation = {
        "id": delegation_id,
        "task": task_description,
        "priority": priority,
        "target_session": target_session,
        "context": context or {},
        "status": "pending",
        "created_at": time.time()
    }

    # In a full implementation, this would be stored in a shared database
    # and made available to other sessions

    return {
        "success": True,
        "delegation_id": delegation_id,
        "delegation": delegation,
        "message": f"Task delegated with ID '{delegation_id}'.",
        "ui_update": "delegation_created"
    }


def get_agent_status(task_id: str) -> Dict[str, Any]:
    """Get the status of a background agent task"""
    state = get_session_state()
    agents = state.get("background_agents", {})

    if task_id not in agents:
        return {"error": f"Unknown agent task: {task_id}"}

    agent = agents[task_id]

    return {
        "success": True,
        "task_id": task_id,
        "agent_info": agent
    }


def list_agents() -> Dict[str, Any]:
    """List all background agent tasks"""
    state = get_session_state()
    agents = state.get("background_agents", {})

    agent_list = []
    for task_id, agent in agents.items():
        agent_list.append({
            "task_id": task_id,
            "type": agent.get("type"),
            "task": agent.get("task", "")[:50],
            "status": agent.get("status"),
            "created_at": agent.get("created_at")
        })

    return {
        "success": True,
        "agents": agent_list,
        "count": len(agent_list)
    }
