"""
MCP Tools Core
Tool execution and definition export
"""

import copy
import logging
from typing import Any, Dict, List

from .schemas import TOOL_DEFINITIONS
from .handlers import (
    # File tools
    read_file, write_file, list_directory, search_files,
    get_file_info, create_directory, move_file, delete_file,
    execute_command, get_task_status, list_background_tasks,
    glob_files, grep_search, edit_file, read_files,
    # Git tools
    git, git_status, git_log, git_diff, git_add, git_commit,
    git_branch, git_checkout, git_pull, git_push, git_clone,
    # Browser tools
    browser, browser_navigate, browser_screenshot, browser_click,
    browser_type, browser_get_text, browser_evaluate, browser_close,
    # Search tools
    web_search, web_fetch,
    # Task tools
    todo_write, todo_read, ask_user, use_skill, tool_search,
    # Planning tools
    enter_plan_mode, exit_plan_mode, summarize_context,
    # Advanced tools
    task, delegate_task,
)

# Skill loader import
try:
    from skill_loader import get_skill_loader
    HAS_SKILL_LOADER = True
except ImportError:
    HAS_SKILL_LOADER = False

logger = logging.getLogger(__name__)

# Tool handlers mapping
TOOL_HANDLERS = {
    # File system tools
    "read_file": read_file,
    "write_file": write_file,
    "list_directory": list_directory,
    "search_files": search_files,
    "get_file_info": get_file_info,
    "create_directory": create_directory,
    "move_file": move_file,
    "delete_file": delete_file,
    # Unified Git tool
    "git": git,
    # Legacy Git tools (backward compatibility)
    "git_status": git_status,
    "git_log": git_log,
    "git_diff": git_diff,
    "git_add": git_add,
    "git_commit": git_commit,
    "git_branch": git_branch,
    "git_checkout": git_checkout,
    "git_pull": git_pull,
    "git_push": git_push,
    "git_clone": git_clone,
    # Unified Browser tool
    "browser": browser,
    # Legacy Browser tools (backward compatibility)
    "browser_navigate": browser_navigate,
    "browser_screenshot": browser_screenshot,
    "browser_click": browser_click,
    "browser_type": browser_type,
    "browser_get_text": browser_get_text,
    "browser_evaluate": browser_evaluate,
    "browser_close": browser_close,
    # Skill tool
    "use_skill": use_skill,
    # Optimized tools
    "glob": glob_files,
    "grep": grep_search,
    "edit": edit_file,
    "read_files": read_files,
    # Background task tools
    "execute_command": execute_command,
    "get_task_status": get_task_status,
    "list_background_tasks": list_background_tasks,
    # Todo task tracking
    "todo_write": todo_write,
    "todo_read": todo_read,
    # User question mechanism
    "ask_user": ask_user,
    # Plan mode
    "enter_plan_mode": enter_plan_mode,
    "exit_plan_mode": exit_plan_mode,
    # Context summarization
    "summarize_context": summarize_context,
    # Specialized agent task
    "task": task,
    # Cross-session delegation
    "delegate_task": delegate_task,
    # Tool search
    "tool_search": tool_search,
}


def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool and return the result"""
    # Check if it's an MCP tool (format: server__toolname)
    if "__" in tool_name:
        try:
            from tool_registry import get_tool_registry
            from mcp_client import call_mcp_tool

            registry = get_tool_registry()

            # Check if tool is active (lazy loading check)
            if not registry.is_active(tool_name):
                if registry.is_deferred(tool_name):
                    return {
                        "error": f"Tool '{tool_name}' is deferred and must be activated first. "
                                 f"Use tool_search with query 'select:{tool_name}' to activate it."
                    }
                else:
                    return {"error": f"Unknown MCP tool: {tool_name}"}

            result = call_mcp_tool(tool_name, tool_input)
            return result
        except Exception as e:
            return {"error": f"MCP tool execution failed: {e}"}

    if tool_name not in TOOL_HANDLERS:
        return {"error": f"Unknown tool: {tool_name}"}

    handler = TOOL_HANDLERS[tool_name]

    try:
        result = handler(**tool_input)
        return result
    except TypeError as e:
        return {"error": f"Invalid arguments for {tool_name}: {e}"}
    except Exception as e:
        return {"error": f"Tool execution failed: {e}"}


def get_tool_definitions() -> List[Dict[str, Any]]:
    """Get all tool definitions for sending to Claude.

    Dynamically generates the use_skill tool description based on available skills.
    """
    # Make a deep copy to avoid modifying the original
    tools = copy.deepcopy(TOOL_DEFINITIONS)

    # Dynamically build skill list for use_skill tool
    if HAS_SKILL_LOADER:
        try:
            loader = get_skill_loader()
            loader.reload()

            skill_entries = []
            for skill in loader.skills.values():
                desc = skill.description or f"Skill for {skill.name} related tasks"
                skill_entries.append(f"- {skill.name}: {desc}")

            skill_list = "\n".join(skill_entries) if skill_entries else "No skills available"

            dynamic_description = f"""Execute a skill to help complete specific types of tasks.

Available skills:
{skill_list}

When to use this tool:
- When the user explicitly mentions a skill name (e.g., "/pptx", "/pdf")
- When the user's request clearly matches a skill's purpose

Call this tool with the skill_name and the user's original request."""

            for tool in tools:
                if tool["name"] == "use_skill":
                    tool["description"] = dynamic_description
                    break

        except Exception as e:
            for tool in tools:
                if tool["name"] == "use_skill":
                    tool["description"] = f"Execute a skill (skill loading error: {e})"
                    break
    else:
        for tool in tools:
            if tool["name"] == "use_skill":
                tool["description"] = "Execute a skill (skill loader not installed)"
                break

    # Add only ACTIVE MCP tools (lazy loading pattern)
    try:
        from tool_registry import get_tool_registry

        registry = get_tool_registry()

        active_mcp_tools = registry.get_active_tools()
        if active_mcp_tools:
            tools.extend(active_mcp_tools)

        # Update tool_search description with deferred tools list
        deferred = registry.get_deferred_tools()
        if deferred:
            deferred_list = "\n".join([f"- {t['name']}" for t in deferred])
            for tool in tools:
                if tool["name"] == "tool_search":
                    tool["description"] += f"\n\n**Available deferred tools (must be loaded before use):**\n{deferred_list}"
                    break

    except Exception as e:
        logger.warning(f"Failed to load tool registry: {e}")

    return tools
