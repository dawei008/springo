"""
Session State Management for FastAPI
Tracks todos, plan mode, pending questions, working directory, and active skill.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

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

# Current session ID (set when session switches)
_current_session_id: str = ""

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
    reset_tool_usage()


def update_session_state(key: str, value: Any):
    """Update a specific key in session state"""
    _session_state[key] = value


def get_todos() -> List[Dict]:
    """Get current todo list"""
    return _session_state.get("todos", [])


def set_todos(todos: list):
    """Set todo list"""
    _session_state["todos"] = todos


# ============ Todo Persistence ============
# Todos are saved independently from conversation messages so they
# survive context compaction.  Storage: ~/.springo/sessions/{id}/todos.json

def _todos_path(session_id: str) -> str:
    base = os.path.expanduser("~/.springo/sessions")
    return os.path.join(base, session_id, "todos.json")


def set_current_session_id(session_id: str):
    """Track which session is active (called on session switch).
    Resets tool usage tracking when switching to a different session."""
    global _current_session_id
    if session_id != _current_session_id:
        reset_tool_usage()
    _current_session_id = session_id


def get_current_session_id() -> str:
    return _current_session_id


def persist_todos(session_id: str = "", todos: list = None):
    """Write current todos to disk for the given session."""
    sid = session_id or _current_session_id
    if not sid:
        return
    items = todos if todos is not None else _session_state.get("todos", [])
    if not items:
        # Remove stale file if no todos
        path = _todos_path(sid)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        return
    path = _todos_path(sid)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"persist_todos failed for {sid}: {e}")


def load_todos(session_id: str) -> List[Dict]:
    """Load todos from disk for a session.  Returns [] if none."""
    path = _todos_path(session_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.debug(f"load_todos failed for {session_id}: {e}")
        return []


def format_todos_for_context(todos: list = None) -> str:
    """Format todos as a text block suitable for injection into compaction
    summary or system prompt.  Returns empty string if no todos."""
    items = todos if todos is not None else _session_state.get("todos", [])
    if not items:
        return ""
    lines = ["## Active Task List (persistent, survives compaction)", ""]
    for i, t in enumerate(items, 1):
        status = t.get("status", "pending")
        icon = {"completed": "[x]", "in_progress": "[>]", "pending": "[ ]"}.get(status, "[ ]")
        lines.append(f"{i}. {icon} {t.get('content', '')}  ({status})")
    return "\n".join(lines)


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


# ============ Tool Usage Tracking (Auto-Unload) ============
# Tracks which tools are actually used per session so unused tools
# can be evicted from the context window after a grace period.

_tool_used_in_session: set = set()  # tool names used at least once
_user_turn_counter: int = 0         # number of user messages processed

# Grace period: include all tools for the first N user messages.
# After this, only include core + recently-used tools.
TOOL_GRACE_TURNS: int = 2


def increment_user_turn() -> int:
    """Increment the user turn counter (called at start of each user message processing)."""
    global _user_turn_counter
    _user_turn_counter += 1
    return _user_turn_counter


def get_user_turn() -> int:
    """Get current user turn counter."""
    return _user_turn_counter


def record_tool_usage(tool_name: str):
    """Record that a tool was used in this session."""
    _tool_used_in_session.add(tool_name)


def get_used_tools() -> set:
    """Get set of tool names used in this session."""
    return _tool_used_in_session


def reset_tool_usage():
    """Reset tool usage tracking (called on session switch)."""
    global _tool_used_in_session, _user_turn_counter
    _tool_used_in_session = set()
    _user_turn_counter = 0


__all__ = [
    'get_session_state', 'reset_session_state', 'update_session_state',
    'get_todos', 'set_todos',
    'is_plan_mode', 'set_plan_mode',
    'get_pending_question', 'set_pending_question', 'clear_pending_question',
    'set_working_dir', 'get_working_dir',
    'set_current_session_id', 'get_current_session_id',
    'persist_todos', 'load_todos', 'format_todos_for_context',
    'increment_user_turn', 'get_user_turn',
    'record_tool_usage', 'get_used_tools', 'reset_tool_usage',
    'TOOL_GRACE_TURNS',
]
