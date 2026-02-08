"""
Session State Management
Tracks todos, plan mode, pending questions, and background agents
"""

from typing import Any, Dict

# Session state for current conversation
_session_state: Dict[str, Any] = {
    "todos": [],
    "plan_mode": False,
    "plan_reason": "",
    "pending_plan": None,
    "pending_question": None,
    "context_summary": None,
    "background_agents": {},
    "active_skill": None  # Claude Code style: store activated skill for injection
}


def get_session_state() -> Dict[str, Any]:
    """Get current session state"""
    return _session_state


def reset_session_state():
    """Reset session state"""
    global _session_state
    _session_state = {
        "todos": [],
        "plan_mode": False,
        "plan_reason": "",
        "pending_plan": None,
        "pending_question": None,
        "context_summary": None,
        "background_agents": {},
        "active_skill": None
    }


def update_session_state(key: str, value: Any):
    """Update a specific key in session state"""
    global _session_state
    _session_state[key] = value


def get_todos():
    """Get current todo list"""
    return _session_state.get("todos", [])


def set_todos(todos: list):
    """Set todo list"""
    _session_state["todos"] = todos


def is_plan_mode() -> bool:
    """Check if currently in plan mode"""
    return _session_state.get("plan_mode", False)


def set_plan_mode(enabled: bool, reason: str = ""):
    """Set plan mode status"""
    _session_state["plan_mode"] = enabled
    _session_state["plan_reason"] = reason


def get_pending_question() -> Dict[str, Any]:
    """Get pending question for user"""
    return _session_state.get("pending_question")


def set_pending_question(question: Dict[str, Any]):
    """Set pending question for user"""
    _session_state["pending_question"] = question


def clear_pending_question():
    """Clear pending question"""
    _session_state["pending_question"] = None


def get_background_agents() -> Dict[str, Any]:
    """Get background agents"""
    return _session_state.get("background_agents", {})


def add_background_agent(agent_id: str, agent_info: Dict[str, Any]):
    """Add a background agent"""
    _session_state["background_agents"][agent_id] = agent_info


def remove_background_agent(agent_id: str):
    """Remove a background agent"""
    if agent_id in _session_state["background_agents"]:
        del _session_state["background_agents"][agent_id]


# ==================== Active Skill Management (Claude Code Style) ====================

def get_active_skill() -> Dict[str, Any]:
    """Get currently activated skill for system prompt injection"""
    return _session_state.get("active_skill")


def set_active_skill(skill_info: Dict[str, Any]):
    """Set active skill - will be injected into next system prompt

    skill_info should contain:
    - name: skill name
    - instructions: full skill instructions
    - user_request: original user request (optional)
    """
    _session_state["active_skill"] = skill_info


def clear_active_skill():
    """Clear active skill after it has been injected"""
    _session_state["active_skill"] = None


def consume_active_skill() -> Dict[str, Any]:
    """Get and clear active skill (one-time consumption for injection)"""
    skill = _session_state.get("active_skill")
    _session_state["active_skill"] = None
    return skill
