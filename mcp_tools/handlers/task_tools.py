"""
Task Management Tools
Todo tracking, user questions, skills, and tool search
"""

import logging
from typing import Any, Dict, List

from ..session import get_session_state, set_pending_question

logger = logging.getLogger(__name__)

# Skill loader import
try:
    from api.services.skill_loader import get_skill_loader
    HAS_SKILL_LOADER = True
except ImportError:
    HAS_SKILL_LOADER = False


def todo_write(todos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Create or update the task list"""
    state = get_session_state()
    state["todos"] = todos

    # Persist to disk so todos survive context compaction
    try:
        from api.services.session_state import persist_todos
        persist_todos(todos=todos)
    except Exception:
        pass

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


def use_skill(skill_name: str, user_request: str = "", inject_mode: str = "system") -> Dict[str, Any]:
    """Activate a skill with flexible injection mode

    Args:
        skill_name: Name of the skill to activate
        user_request: Original user request context
        inject_mode: How to inject skill instructions
            - "system" (default, Claude Code style): Inject into system prompt
            - "result": Return instructions in tool_result (original style)

    Both modes are supported for flexibility:
    - "system" mode: Cleaner context, instructions in system prompt
    - "result" mode: Instructions visible in tool_result, useful for debugging
    """
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

        # Build skill instructions
        instructions = f"""<skill name="{skill.name}">
{skill.instructions}
</skill>

IMPORTANT: You have activated the '{skill.name}' skill.
Please follow the instructions above to complete the user's request.
User's original request: {user_request if user_request else '(not specified)'}

Now proceed with the task using the skill instructions."""

        if inject_mode == "result":
            # Original style: return instructions in tool_result
            return {
                "success": True,
                "skill_name": skill.name,
                "skill_activated": True,
                "inject_mode": "result",
                "instructions": instructions,
                "message": f"Skill '{skill.name}' activated. Follow the instructions above."
            }
        else:
            # Claude Code style (default): store for system prompt injection
            # Use the router-level state so messages.py can consume it
            skill_info = {
                "name": skill.name,
                "instructions": skill.instructions,
                "user_request": user_request
            }
            try:
                from api.routers.skills import set_active_skill as set_router_skill
                set_router_skill(skill_info)
            except ImportError:
                pass

            return {
                "success": True,
                "skill_name": skill.name,
                "skill_activated": True,
                "inject_mode": "system",
                "message": f"Skill '{skill.name}' activated and will be applied to next response."
            }
    except Exception as e:
        return {"error": f"Failed to load skill: {str(e)}"}


def manage_skill(action: str, name: str = "", description: str = "",
                  instructions: str = "", triggers: str = "") -> Dict[str, Any]:
    """Create, update, or delete a reusable skill from conversation experience.

    Args:
        action: "create", "update", "delete", or "list"
        name: Skill name (kebab-case, e.g. "deploy-ecs-service")
        description: One-line description of what the skill does
        instructions: Full markdown instructions the agent should follow
        triggers: Comma-separated trigger phrases (optional)
    """
    import os
    from pathlib import Path

    skills_dir = Path(os.path.expanduser("~/.springo/skills"))
    skills_dir.mkdir(parents=True, exist_ok=True)

    if action == "list":
        if not HAS_SKILL_LOADER:
            return {"error": "Skill loader not available"}
        loader = get_skill_loader()
        loader.reload(force=True)
        return {
            "success": True,
            "skills": [
                {"name": s.name, "description": s.description}
                for s in loader.skills.values()
            ],
            "count": len(loader.skills),
        }

    if not name:
        return {"error": "name is required for create/update/delete"}

    # Sanitize name to kebab-case directory name
    safe_name = name.lower().replace(" ", "-")
    skill_dir = skills_dir / safe_name

    if action == "delete":
        if not skill_dir.exists():
            return {"error": f"Skill '{safe_name}' not found"}
        import shutil
        shutil.rmtree(skill_dir)
        if HAS_SKILL_LOADER:
            get_skill_loader().force_reload()
        return {"success": True, "message": f"Skill '{safe_name}' deleted"}

    if action in ("create", "update"):
        if not instructions:
            return {"error": "instructions is required for create/update"}

        if action == "create" and skill_dir.exists():
            return {"error": f"Skill '{safe_name}' already exists. Use action='update' to modify it."}

        if action == "update" and not skill_dir.exists():
            return {"error": f"Skill '{safe_name}' not found. Use action='create' to create it."}

        skill_dir.mkdir(parents=True, exist_ok=True)

        # Build SKILL.md with YAML frontmatter
        frontmatter_lines = [
            "---",
            f"name: {safe_name}",
            f"description: {description}" if description else f"description: Skill for {safe_name}",
        ]
        if triggers:
            frontmatter_lines.append(f"triggers: {triggers}")
        frontmatter_lines.append("---")
        frontmatter_lines.append("")

        skill_md = "\n".join(frontmatter_lines) + instructions

        (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

        if HAS_SKILL_LOADER:
            get_skill_loader().force_reload()

        return {
            "success": True,
            "action": action,
            "skill_name": safe_name,
            "path": str(skill_dir),
            "message": f"Skill '{safe_name}' {'created' if action == 'create' else 'updated'} at {skill_dir}",
        }

    return {"error": f"Unknown action: {action}. Use create, update, delete, or list."}


def tool_search(query: str, auto_activate: bool = True, max_results: int = 5) -> Dict[str, Any]:
    """Search for deferred tools and optionally auto-activate the best match.

    When auto_activate=True, this will:
    1. Search for matching tools
    2. Start the MCP server if needed
    3. Activate the best matching tool
    """
    try:
        from api.services.tool_registry import get_tool_registry
        from api.services.mcp_client import get_external_mcp_manager

        registry = get_tool_registry()
        manager = get_external_mcp_manager()

        def activate_tool_with_server(tool_name: str) -> Dict[str, Any]:
            """Activate a tool by starting its server if needed"""
            # Record usage so auto-unload keeps this tool alive
            try:
                from api.services.session_state import record_tool_usage
                record_tool_usage(tool_name)
            except Exception:
                pass

            # Already active?
            if registry.is_active(tool_name):
                return {
                    "success": True,
                    "tool_name": tool_name,
                    "message": f"Tool '{tool_name}' is already active."
                }

            # Extract server name
            if "__" not in tool_name:
                return {"error": f"Invalid tool name format: {tool_name}"}

            server_name = tool_name.split("__")[0]

            # Start server if not running
            if server_name not in manager.servers:
                if not manager.ensure_server_started(server_name):
                    if server_name not in manager.server_configs:
                        return {"error": f"MCP server '{server_name}' is not configured. Add it to ~/.springo/mcp_servers.json"}
                    return {"error": f"Failed to start MCP server: {server_name}"}

            # Get tool definition from running server
            if server_name in manager.servers:
                server = manager.servers[server_name]
                for tool_def in server.get_tool_definitions():
                    if tool_def.get("name") == tool_name:
                        registry.activate(tool_name, tool_def)
                        return {
                            "success": True,
                            "tool_name": tool_name,
                            "tool": tool_def,
                            "message": f"Tool '{tool_name}' is now active and ready to use."
                        }

            return {"error": f"Tool '{tool_name}' not found on server {server_name}"}

        # Direct selection with select: prefix
        if query.startswith("select:"):
            tool_name = query[7:].strip()
            result = activate_tool_with_server(tool_name)
            if "error" in result:
                return result
            return {
                "success": True,
                "action": "activated",
                **result
            }

        # Search for tools in deferred registry
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
            result = activate_tool_with_server(tool_name)
            if result.get("success"):
                return {
                    "success": True,
                    "action": "auto_activated",
                    "tool_name": tool_name,
                    "tool": result.get("tool"),
                    "search_results": results,
                    "message": f"Auto-activated best match: '{tool_name}'. You can now use this tool."
                }
            # If activation failed but we have results, return them
            return {
                "success": True,
                "action": "search",
                "query": query,
                "results": results,
                "count": len(results),
                "activation_error": result.get("error"),
                "message": f"Found {len(results)} tools but auto-activation failed. Use select:<tool_name> to try manually."
            }

        # No results found — try to discover tools from uncached servers matching the query
        if not results:
            configured = manager.get_configured_servers()
            enabled = [s['name'] for s in configured if s.get('enabled', True)]

            # Check if query matches a configured server that has no cached tools
            matching_servers = [
                s['name'] for s in configured
                if s.get('enabled', True) and query_lower in s['name'].lower()
                and s.get('cached_tools', 0) == 0 and not s.get('running')
            ]

            if matching_servers:
                # Auto-discover: start server, cache tools, register deferred, search again
                for server_name in matching_servers:
                    try:
                        if manager.ensure_server_started(server_name):
                            logger.info(f"tool_search auto-discovered server: {server_name}")
                    except Exception as e:
                        logger.warning(f"tool_search failed to auto-discover {server_name}: {e}")

                # Re-search now that new tools are registered
                new_deferred = registry.get_deferred_tools()
                scored_retry = []
                for tool in new_deferred:
                    name = tool.get("name", "").lower()
                    desc = tool.get("description", "").lower()
                    score = 0
                    if query_lower in name:
                        score += 10
                    for word in query_lower.split():
                        if word in name:
                            score += 5
                        if word in desc:
                            score += 2
                    if score > 0:
                        scored_retry.append((score, tool))
                scored_retry.sort(key=lambda x: x[0], reverse=True)
                results = [t[1] for t in scored_retry[:max_results]]

                if results and auto_activate:
                    best_match = results[0]
                    tool_name = best_match.get("name")
                    result = activate_tool_with_server(tool_name)
                    if result.get("success"):
                        return {
                            "success": True,
                            "action": "auto_discovered_and_activated",
                            "tool_name": tool_name,
                            "tool": result.get("tool"),
                            "search_results": results,
                            "discovered_servers": matching_servers,
                            "message": f"Auto-discovered server '{matching_servers[0]}' and activated '{tool_name}'. Ready to use."
                        }

                if results:
                    return {
                        "success": True,
                        "action": "auto_discovered",
                        "query": query,
                        "results": results,
                        "count": len(results),
                        "discovered_servers": matching_servers,
                        "message": f"Auto-discovered {len(results)} tools from server(s): {', '.join(matching_servers)}. Use select:<tool_name> to activate."
                    }

            return {
                "success": True,
                "action": "search",
                "query": query,
                "results": [],
                "count": 0,
                "available_servers": enabled,
                "message": f"No matching tools found. Available MCP servers: {', '.join(enabled)}. Try a different query or use server__toolname format."
            }

        return {
            "success": True,
            "action": "search",
            "query": query,
            "results": results,
            "count": len(results),
            "message": f"Found {len(results)} matching tools. Use select:<tool_name> to activate."
        }

    except ImportError as e:
        return {"error": f"Tool registry not available: {e}"}
    except Exception as e:
        return {"error": f"Tool search failed: {str(e)}"}
