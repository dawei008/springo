"""
Planning Tools
Plan mode and context summarization
"""

from typing import Any, Dict

from ..session import get_session_state


def enter_plan_mode(reason: str = "") -> Dict[str, Any]:
    """Enter plan mode - signal Claude to create a plan before executing"""
    state = get_session_state()
    state["plan_mode"] = True
    state["plan_reason"] = reason

    return {
        "success": True,
        "plan_mode": True,
        "reason": reason,
        "message": "Entered plan mode. Please create a plan before executing.",
        "ui_update": "plan_mode"
    }


def exit_plan_mode(plan: Dict[str, Any] = None) -> Dict[str, Any]:
    """Exit plan mode and optionally submit a plan for approval"""
    state = get_session_state()
    state["plan_mode"] = False

    if plan:
        state["pending_plan"] = plan
        return {
            "success": True,
            "plan_mode": False,
            "plan_submitted": True,
            "plan": plan,
            "message": "Plan submitted for approval.",
            "ui_update": "plan_approval"
        }

    return {
        "success": True,
        "plan_mode": False,
        "message": "Exited plan mode.",
        "ui_update": "plan_mode"
    }


def summarize_context(summary: str, key_points: list = None) -> Dict[str, Any]:
    """Create a context summary for resumption"""
    state = get_session_state()

    context_summary = {
        "summary": summary,
        "key_points": key_points or [],
        "todos": state.get("todos", []),
        "plan_mode": state.get("plan_mode", False)
    }

    state["context_summary"] = context_summary

    return {
        "success": True,
        "context_summary": context_summary,
        "message": "Context summary created. This can be used to resume the conversation."
    }


def get_context_summary() -> Dict[str, Any]:
    """Get the current context summary"""
    state = get_session_state()
    context_summary = state.get("context_summary")

    if context_summary:
        return {
            "success": True,
            "has_summary": True,
            "context_summary": context_summary
        }

    return {
        "success": True,
        "has_summary": False,
        "message": "No context summary available."
    }
