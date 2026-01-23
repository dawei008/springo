"""
Task Management Tools
Todo tracking, user questions, skills, and tool search
"""

from typing import Any, Dict, List

from ..session import get_session_state, set_pending_question

# Skill loader import
try:
    from skill_loader import get_skill_loader
    HAS_SKILL_LOADER = True
except ImportError:
    HAS_SKILL_LOADER = False


def todo_write(todos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Create or update the task list"""
    state = get_session_state()
    state["todos"] = todos

    completed = sum(1 for t in todos if t.get("status") == "completed")
    in_progress = sum(1 for t in todos if t.get("status") == "in_progress")
    pending = sum(1 for t in todos if t.get("status") == "pending")

    return {
        "success": True,
        "todos": todos,
        "stats": {
            "total": len(todos),
            "completed": completed,
            "in_progress": in_progress,
            "pending": pending
        },
        "ui_update": "todo_panel"
    }


def todo_read() -> Dict[str, Any]:
    """Read the current task list"""
    state = get_session_state()
    todos = state.get("todos", [])

    completed = sum(1 for t in todos if t.get("status") == "completed")
    in_progress = sum(1 for t in todos if t.get("status") == "in_progress")
    pending = sum(1 for t in todos if t.get("status") == "pending")

    return {
        "todos": todos,
        "stats": {
            "total": len(todos),
            "completed": completed,
            "in_progress": in_progress,
            "pending": pending
        }
    }


def ask_user(question: str, options: List[Dict[str, Any]], allow_custom: bool = True) -> Dict[str, Any]:
    """Ask the user a question and wait for their response"""
    question_data = {
        "question": question,
        "options": options,
        "allow_custom": allow_custom,
        "awaiting_response": True
    }

    set_pending_question(question_data)

    return {
        "success": True,
        "waiting_for_user": True,
        "question": question,
        "options": options,
        "message": "Question sent to user. Waiting for response.",
        "ui_update": "user_question"
    }


def use_skill(skill_name: str, user_request: str = "") -> Dict[str, Any]:
    """Activate a skill and return its instructions"""
    if not HAS_SKILL_LOADER:
        return {"error": "Skill loader not available"}

    try:
        loader = get_skill_loader()
        skill = loader.get_skill(skill_name)

        if not skill:
            available = [s.name for s in loader.skills.values()]
            return {
                "error": f"Skill '{skill_name}' not found",
                "available_skills": available
            }

        instructions = f"""<skill name="{skill.name}">
{skill.instructions}
</skill>

IMPORTANT: You have activated the '{skill.name}' skill.
Please follow the instructions above to complete the user's request.
User's original request: {user_request if user_request else '(not specified)'}

Now proceed with the task using the skill instructions."""

        return {
            "success": True,
            "skill_name": skill.name,
            "skill_activated": True,
            "instructions": instructions,
            "message": f"Skill '{skill.name}' activated. Follow the instructions above."
        }
    except Exception as e:
        return {"error": f"Failed to load skill: {str(e)}"}


def tool_search(query: str, auto_activate: bool = True, max_results: int = 5) -> Dict[str, Any]:
    """Search for deferred tools and optionally auto-activate the best match"""
    try:
        from tool_registry import get_tool_registry

        registry = get_tool_registry()

        # Direct selection with select: prefix
        if query.startswith("select:"):
            tool_name = query[7:]  # Remove "select:" prefix
            if registry.activate_tool(tool_name):
                tool_def = registry.get_tool_definition(tool_name)
                return {
                    "success": True,
                    "action": "activated",
                    "tool_name": tool_name,
                    "tool": tool_def,
                    "message": f"Tool '{tool_name}' is now active and ready to use."
                }
            else:
                return {"error": f"Tool '{tool_name}' not found or could not be activated"}

        # Search for tools
        deferred_tools = registry.get_deferred_tools()
        query_lower = query.lower()

        # Score and rank tools
        scored_tools = []
        for tool in deferred_tools:
            name = tool.get("name", "").lower()
            desc = tool.get("description", "").lower()

            score = 0
            # Exact name match
            if query_lower in name:
                score += 10
            # Word matches in name
            for word in query_lower.split():
                if word in name:
                    score += 5
                if word in desc:
                    score += 2

            if score > 0:
                scored_tools.append((score, tool))

        # Sort by score
        scored_tools.sort(key=lambda x: x[0], reverse=True)
        results = [t[1] for t in scored_tools[:max_results]]

        # Auto-activate best match if requested
        if auto_activate and results:
            best_match = results[0]
            tool_name = best_match.get("name")
            if registry.activate_tool(tool_name):
                tool_def = registry.get_tool_definition(tool_name)
                return {
                    "success": True,
                    "action": "auto_activated",
                    "tool_name": tool_name,
                    "tool": tool_def,
                    "search_results": results,
                    "message": f"Auto-activated best match: '{tool_name}'. You can now use this tool."
                }

        return {
            "success": True,
            "action": "search",
            "query": query,
            "results": results,
            "count": len(results),
            "message": f"Found {len(results)} matching tools. Use select:<tool_name> to activate."
        }

    except ImportError:
        return {"error": "Tool registry not available"}
    except Exception as e:
        return {"error": f"Tool search failed: {str(e)}"}
