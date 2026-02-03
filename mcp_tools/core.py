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
    # Browser tools removed - use MCP playwright instead
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
    # Browser tools removed - use MCP playwright instead
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
            from mcp_client import call_mcp_tool, get_mcp_manager

            registry = get_tool_registry()
            manager = get_mcp_manager()

            # Extract server name from tool name
            server_name = tool_name.split("__")[0]

            # Auto-activate: ensure server is started and tool is registered
            if not registry.is_active(tool_name):
                # Start the server if not running (lazy loading)
                if server_name not in manager.servers:
                    if not manager.ensure_server_started(server_name):
                        return {"error": f"Failed to start MCP server: {server_name}"}

                # Register/activate the tool from the running server
                if server_name in manager.servers:
                    server = manager.servers[server_name]
                    for tool_def in server.get_tool_definitions():
                        if tool_def.get("name") == tool_name:
                            registry.activate(tool_name, tool_def)
                            break

                # Final check
                if not registry.is_active(tool_name):
                    return {"error": f"Tool '{tool_name}' not found on server {server_name}"}

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

            dynamic_description = f"""Execute a skill to complete specialized tasks like document creation, data processing, etc.

**CRITICAL: When a skill matches the user's request, you MUST invoke this tool IMMEDIATELY.**
- NEVER pretend to create files (PPT, Word, Excel, PDF) without calling this tool first
- NEVER announce "I'll create..." and then just output text - actually call the tool
- This is a BLOCKING REQUIREMENT: invoke the skill tool BEFORE generating file-related responses

Available skills:
{skill_list}

When to use this tool:
- User explicitly mentions a skill (e.g., "/pptx", "/pdf")
- User asks to CREATE documents: PPT, Word, Excel, PDF -> use corresponding skill
- User asks to EDIT existing documents -> use corresponding skill
- Task matches a skill's description above

Example: User says "create a presentation about X" -> MUST call use_skill(skill_name="pptx")

Call with skill_name and optionally user_request. The skill will provide detailed implementation."""

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

    # Add MCP tools (lazy loading pattern with caching)
    try:
        from tool_registry import get_tool_registry
        from mcp_client import get_mcp_manager

        registry = get_tool_registry()
        manager = get_mcp_manager()

        # Get active tools (already loaded from running servers)
        active_mcp_tools = registry.get_active_tools()
        active_tool_names = {t['name'] for t in active_mcp_tools} if active_mcp_tools else set()

        if active_mcp_tools:
            tools.extend(active_mcp_tools)

        # Add cached MCP tool placeholders for enabled servers (lazy loading)
        # These allow Claude to call MCP tools directly without needing to search first
        configured_servers = manager.get_configured_servers()
        enabled_server_names = {
            s['name'] for s in configured_servers
            if s.get('enabled', True) and s.get('status') != 'disabled'
        }

        # Get cached tools from previous server discoveries
        cached_tools = manager.get_cached_tools()

        for server_name, server_tools in cached_tools.items():
            if server_name in enabled_server_names:
                for tool_def in server_tools:
                    # Don't add if already active (server is running and tool is loaded)
                    if tool_def['name'] not in active_tool_names:
                        # Add note that this tool will auto-activate
                        placeholder_tool = copy.deepcopy(tool_def)
                        if "(Auto-loads" not in placeholder_tool.get('description', ''):
                            placeholder_tool['description'] = placeholder_tool.get('description', '') + " (Auto-loads on first use)"
                        tools.append(placeholder_tool)
                        active_tool_names.add(tool_def['name'])  # Prevent duplicates

        # Also list all available servers in tool_search for discovery of other tools
        deferred = registry.get_deferred_tools()
        enabled_servers = [s for s in configured_servers if s.get('enabled', True) and s.get('status') != 'disabled']

        mcp_info_parts = []

        if deferred:
            deferred_list = "\n".join([f"- {t['name']}" for t in deferred[:30]])
            mcp_info_parts.append(f"**Activated MCP tools:**\n{deferred_list}")

        if enabled_servers:
            server_list = []
            for s in enabled_servers:
                name = s['name']
                desc = s.get('description', '')
                running = s.get('running', False)
                tools_count = s.get('tools', 0)
                cached_count = len(cached_tools.get(name, []))
                if running:
                    status = f"({tools_count} tools)"
                elif cached_count > 0:
                    status = f"({cached_count} cached tools, auto-loads)"
                else:
                    status = "(not loaded yet)"
                server_list.append(f"- {name}: {desc} {status}")

            mcp_info_parts.append(f"**Available MCP servers:**\n" + "\n".join(server_list))
            mcp_info_parts.append("Use tool_search to discover more tools from these servers.")

        if mcp_info_parts:
            for tool in tools:
                if tool["name"] == "tool_search":
                    tool["description"] += "\n\n" + "\n\n".join(mcp_info_parts)
                    break

    except Exception as e:
        logger.warning(f"Failed to load tool registry: {e}")

    return tools
