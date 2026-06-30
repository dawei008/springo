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
    # Browser extension tools (drive the user's real Chrome)
    web_browser_status, web_navigate, web_click, web_type,
    web_read_page, web_screenshot, web_evaluate, web_tabs,
    # Search tools
    web_search, web_fetch,
    # Task tools
    todo_write, todo_read, ask_user, use_skill, skill_view, manage_skill, tool_search,
    # Planning tools
    enter_plan_mode, exit_plan_mode, summarize_context,
    # Advanced tools
    task, delegate_task,
    # Scheduler tools
    scheduler,
    # Team communication tools
    team_send_message, team_task_create, team_task_update,
    team_task_list, team_task_get,
    # LSP code intelligence tools
    lsp_go_to_definition, lsp_find_references, lsp_hover,
    lsp_document_symbols, lsp_workspace_symbol, lsp_diagnostics,
    # Memory tools
    memory_search, memory_get, memory_write,
    # Knowledge base tools
    kb_list, kb_search, kb_read_page, kb_write_page,
    kb_ingest_text, kb_ingest_file, kb_ingest_pdf, kb_lint, kb_stats,
    # ACP agent tools
    acp_prompt, acp_list_agents, acp_new_session,
    # Computer use
    computer,
    # Canvas operations (list/read/patch/query/dispatch artifacts)
    canvas,
)

# Skill loader import
try:
    from api.services.skill_loader import get_skill_loader
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
    # Browser extension tools (drive the user's real signed-in Chrome)
    "web_browser_status": web_browser_status,
    "web_navigate": web_navigate,
    "web_click": web_click,
    "web_type": web_type,
    "web_read_page": web_read_page,
    "web_screenshot": web_screenshot,
    "web_evaluate": web_evaluate,
    "web_tabs": web_tabs,
    # Skill tools
    "use_skill": use_skill,
    "skill_view": skill_view,
    "manage_skill": manage_skill,
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
    # Scheduler
    "scheduler": scheduler,
    # Team communication tools (only functional in team context)
    "send_message": team_send_message,
    "task_create": team_task_create,
    "task_update": team_task_update,
    "task_list": team_task_list,
    "task_get": team_task_get,
    # LSP code intelligence tools
    "lsp_go_to_definition": lsp_go_to_definition,
    "lsp_find_references": lsp_find_references,
    "lsp_hover": lsp_hover,
    "lsp_document_symbols": lsp_document_symbols,
    "lsp_workspace_symbol": lsp_workspace_symbol,
    "lsp_diagnostics": lsp_diagnostics,
    # Memory tools
    "memory_search": memory_search,
    "memory_get": memory_get,
    "memory_write": memory_write,
    # Knowledge base tools
    "kb_list": kb_list,
    "kb_search": kb_search,
    "kb_read_page": kb_read_page,
    "kb_write_page": kb_write_page,
    "kb_ingest_text": kb_ingest_text,
    "kb_ingest_file": kb_ingest_file,
    "kb_ingest_pdf": kb_ingest_pdf,
    "kb_lint": kb_lint,
    "kb_stats": kb_stats,
    # ACP agent tools
    "acp_prompt": acp_prompt,
    "acp_list_agents": acp_list_agents,
    "acp_new_session": acp_new_session,
    # Computer use
    "computer": computer,
    "canvas": canvas,
}


def _run_hook(hook_point: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Run a plugin hook, returning the (possibly modified) data dict.

    Returns the data dict with optional special keys:
      _stop_pipeline: bool — hook chain was stopped (tool blocked)
      _substitute_result: dict — skip execution, return this result instead
    """
    try:
        from api.services.plugin_system.hook_pipeline import get_hook_pipeline, HookContext
        pipeline = get_hook_pipeline()
        # Deep copy to prevent hooks from mutating original caller data
        ctx = HookContext(hook_point=hook_point, data=copy.deepcopy(data))
        ctx = pipeline.execute(hook_point, ctx)
        return ctx.data if not ctx.stop_pipeline else {**ctx.data, "_stop_pipeline": True}
    except Exception as e:
        logger.debug(f"Hook {hook_point} skipped: {e}")
        return data


def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool and return the result (with pre/post hook support)."""

    # === PRE_TOOL_USE hook ===
    pre = _run_hook("pre_tool_use", {"tool_name": tool_name, "tool_input": tool_input})
    if pre.get("_stop_pipeline"):
        return pre.get("result", {"error": f"Tool blocked by plugin: {pre.get('stopped_by', 'unknown')}"})
    if "_substitute_result" in pre:
        return pre["_substitute_result"]
    # Apply any modifications from hooks
    tool_name = pre.get("tool_name", tool_name)
    tool_input = pre.get("tool_input", tool_input)

    # === EXECUTE ===
    result = _execute_tool_inner(tool_name, tool_input)

    # === POST_TOOL_USE hook ===
    post = _run_hook("post_tool_use", {"tool_name": tool_name, "tool_input": tool_input, "result": result})
    result = post.get("result", result)

    return result


def _execute_tool_inner(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Core tool execution logic (MCP + built-in)."""
    # Generic MCP entry: collapses 99 cached MCP tool schemas into one
    # prompt-side tool. The model picks (server, tool, args); we forward to
    # the server__tool path that already handles lazy server start + caching.
    if tool_name == "mcp_call":
        server = (tool_input or {}).get("server", "")
        tool = (tool_input or {}).get("tool", "")
        args = (tool_input or {}).get("args") or {}
        if not server or not tool:
            return {"error": "mcp_call requires both 'server' and 'tool' parameters"}
        # Allow either bare tool name or full "server__tool" — be forgiving.
        if "__" in tool:
            full_name = tool
        else:
            full_name = f"{server}__{tool}"
        return _execute_tool_inner(full_name, args)

    # Check if it's an MCP tool (format: server__toolname)
    if "__" in tool_name:
        try:
            from api.services.tool_registry import get_tool_registry
            from api.services.mcp_client import call_mcp_tool, get_external_mcp_manager

            registry = get_tool_registry()
            manager = get_external_mcp_manager()

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

    # Dynamically build skill list for use_skill tool (progressive disclosure)
    COMPACT_THRESHOLD = 5
    if HAS_SKILL_LOADER:
        try:
            loader = get_skill_loader()
            loader.reload()

            skills_dir = str(loader.skills_dir)
            skill_count = len(loader.skills)
            skill_entries = []
            for skill in loader.skills.values():
                desc = skill.description or f"Skill for {skill.name}"
                skill_entries.append(f"- {skill.name}: {desc[:80]}")

            skill_list = "\n".join(skill_entries) if skill_entries else "No skills available"

            if skill_count <= COMPACT_THRESHOLD:
                dynamic_description = f"""Execute a skill to complete specialized tasks.

**CRITICAL: When a skill matches the user's request, invoke this tool IMMEDIATELY.**

Skills directory: `{skills_dir}/`

Available skills:
{skill_list}

When to use: user mentions a skill name, asks to create documents (PPT, Word, Excel, PDF), or task matches a skill description.
Call with skill_name and optionally user_request."""
            else:
                dynamic_description = f"""Execute a skill to complete specialized tasks.

**CRITICAL: When a skill matches the user's request, invoke this tool IMMEDIATELY.**

Skills directory: `{skills_dir}/`
Total skills: {skill_count}

Skill index (call skill_view for full details):
{skill_list}

Workflow: 1) Match user request to a skill above. 2) Optionally call skill_view(name) to inspect. 3) Call use_skill(skill_name, user_request)."""

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

    # Dynamically adjust memory_search tool based on AgentCore config
    try:
        from api.services.memory_sync import load_memory_config
        mem_cfg = load_memory_config()
        agentcore_enabled = mem_cfg.get("memory_enabled", False) and bool(mem_cfg.get("memory_id", ""))
    except Exception:
        agentcore_enabled = False

    for tool in tools:
        if tool["name"] == "memory_search":
            if agentcore_enabled:
                # Full three-tier description (already the default in schemas.py)
                pass
            else:
                # Local-only: remove longterm scope, simplify description
                tool["description"] = """Search your persistent memory files (memory/*.md, MEMORY.md).

**When to use this tool:**
- Before answering questions about prior conversations, decisions, preferences, or context from previous sessions
- When the user references something discussed "before", "last time", "yesterday", etc.
- When you need to recall stored facts, todos, or project context

Note: MEMORY.md and the last 2 days of daily logs are already injected into your system prompt. Use this tool for searching **older** memory files or when you need targeted recall."""
                tool["input_schema"]["properties"]["scope"] = {
                    "type": "string",
                    "description": "Search scope: 'recent' (local files), 'list' (list all files). AgentCore not configured.",
                    "enum": ["recent", "list"],
                    "default": "recent"
                }
            break

    # MCP tools — single mcp_call entry instead of 100s of placeholder schemas.
    # Active tools (server already running this turn) keep their full schema
    # because the model needs them ready for the next call; everything else
    # is summarized in mcp_call's description and tool_search's index.
    try:
        from api.services.tool_registry import get_tool_registry
        from api.services.mcp_client import get_external_mcp_manager

        registry = get_tool_registry()
        manager = get_external_mcp_manager()

        active_mcp_tools = registry.get_active_tools() or []
        active_tool_names = {t['name'] for t in active_mcp_tools}
        if active_mcp_tools:
            tools.extend(active_mcp_tools)

        configured_servers = manager.get_configured_servers()
        enabled_servers = [
            s for s in configured_servers
            if s.get('enabled', True) and s.get('status') != 'disabled'
        ]
        cached_tools = manager.get_cached_tools()

        # Build the dynamic mcp_call description: one bullet per server +
        # comma-separated cached tool names so the model can pick without
        # paying for each schema.
        server_blocks: List[str] = []
        for s in enabled_servers:
            name = s['name']
            desc = s.get('description', '') or ''
            srv_cached = [
                t.get('name', '').split('__', 1)[1]
                for t in cached_tools
                if t.get('name', '').startswith(name + '__') and t.get('name') not in active_tool_names
            ]
            srv_cached.sort()
            if srv_cached:
                tool_list = ', '.join(srv_cached[:50])
                more = '' if len(srv_cached) <= 50 else f' (+{len(srv_cached) - 50} more — call tool_search)'
                server_blocks.append(f"- **{name}**: {desc}\n    tools: {tool_list}{more}")
            else:
                server_blocks.append(f"- **{name}**: {desc} (no cached tools yet — call tool_search to discover)")
        server_listing = "\n".join(server_blocks) if server_blocks else "(no MCP servers configured)"

        for tool in tools:
            if tool["name"] == "mcp_call":
                tool["description"] = tool["description"].replace("{MCP_SERVER_LIST}", server_listing)
                break

        # tool_search description gets a compact list of currently-activated
        # MCP tools (already in the prompt above as full schemas) so the
        # model knows what it can call without going through mcp_call.
        deferred = registry.get_deferred_tools()
        if deferred:
            deferred_list = "\n".join([f"- {t['name']}" for t in deferred[:30]])
            for tool in tools:
                if tool["name"] == "tool_search":
                    tool["description"] += f"\n\n**Activated MCP tools (full schema in prompt):**\n{deferred_list}"
                    break

    except Exception as e:
        logger.warning(f"Failed to load tool registry: {e}")
        # Even on failure, drop the placeholder marker so the description is sane.
        for tool in tools:
            if tool["name"] == "mcp_call":
                tool["description"] = tool["description"].replace("{MCP_SERVER_LIST}", "(MCP unavailable)")
                break

    return tools


def get_tool_definitions_with_team() -> List[Dict[str, Any]]:
    """Get tool definitions including team communication tools.

    Called by the collaborative agent loop to provide team tools alongside
    the standard tool set.
    """
    tools = get_tool_definitions()

    from .schemas_team import TEAM_TOOL_DEFINITIONS
    tools.extend(copy.deepcopy(TEAM_TOOL_DEFINITIONS))

    return tools


def get_mcp_server_instructions() -> str:
    """Get MCP server instructions for system prompt injection (like Claude Code does).

    Returns a formatted string with instructions from all running MCP servers,
    or empty string if none have instructions.
    """
    try:
        from api.services.mcp_client import get_external_mcp_manager
        manager = get_external_mcp_manager()
        instructions = manager.get_server_instructions()
        if not instructions:
            return ""

        parts = ["\n\n# MCP Server Instructions\n",
                 "The following MCP servers have provided instructions for how to use their tools:\n"]
        for name, text in instructions.items():
            # Truncate very long instructions to avoid bloating context
            truncated = text[:2000] + "..." if len(text) > 2000 else text
            parts.append(f"\n## {name}\n{truncated}\n")
        return "".join(parts)
    except Exception as e:
        logger.warning(f"Failed to get MCP server instructions: {e}")
        return ""
