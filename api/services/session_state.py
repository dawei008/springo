"""
Session State Management for FastAPI
Tracks todos, plan mode, pending questions, working directory, and active skill.
Tracks todos, plan mode, pending questions, working directory, and active skill.
"""

import os
from typing import Any, Dict, List, Optional


# Session state for current conversation
_session_state: Dict[str, Any] = {
    "todos": [],
    "plan_mode": False,
    "plan_reason": "",
    "pending_plan": None,
    "pending_question": None,
    "context_summary": None,
    "background_agents": {},
    "active_skill": None,
}

# Working directory (set by user from UI)
_working_dir: str = ""


# ============ Session State ============

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
        "active_skill": None,
    }


def update_session_state(key: str, value: Any):
    """Update a specific key in session state"""
    _session_state[key] = value


def get_todos() -> List[Dict]:
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


def get_pending_question() -> Optional[Dict[str, Any]]:
    """Get pending question for user"""
    return _session_state.get("pending_question")


def set_pending_question(question: Dict[str, Any]):
    """Set pending question for user"""
    _session_state["pending_question"] = question


def clear_pending_question():
    """Clear pending question"""
    _session_state["pending_question"] = None


# ============ Working Directory ============

def set_working_dir(path: str):
    """Set the current working directory for tool operations"""
    global _working_dir
    _working_dir = os.path.abspath(os.path.expanduser(path)) if path else ""


def get_working_dir() -> str:
    """Get the current working directory"""
    return _working_dir


__all__ = [
    'get_session_state', 'reset_session_state', 'update_session_state',
    'get_todos', 'set_todos',
    'is_plan_mode', 'set_plan_mode',
    'get_pending_question', 'set_pending_question', 'clear_pending_question',
    'set_working_dir', 'get_working_dir',
]
