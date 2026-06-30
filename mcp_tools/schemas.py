"""
Tool Definitions Schema
JSON schemas for all MCP tools sent to Claude
"""

TOOL_DEFINITIONS = [
    {
        "name": "mcp_call",
        "description": (
            "Invoke any tool on a configured MCP server. The server's full tool "
            "schema is loaded on first use, so we don't pay the prompt cost for "
            "all tools up front.\n\n"
            "**Workflow:**\n"
            "1. Pick a `server` from the list in this description.\n"
            "2. If you don't know the exact `tool` name, call `tool_search(query=..., "
            "auto_activate=true)` first — it lists every cached MCP tool.\n"
            "3. Call `mcp_call(server=..., tool=..., args={...})` with the JSON "
            "args the tool expects.\n\n"
            "Available servers (list filled in dynamically):\n"
            "{MCP_SERVER_LIST}"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "MCP server name, e.g. 'github'"},
                "tool":   {"type": "string", "description": "Tool name on the server (without 'server__' prefix)"},
                "args":   {"type": "object", "description": "JSON arguments forwarded to the tool"},
            },
            "required": ["server", "tool"],
        },
    },
    {
        "name": "tool_search",
        "description": """Search for deferred tools and optionally auto-activate the best match.

**IMPORTANT: Use auto_activate=true to save time!**

When you need to use an MCP tool, call this with auto_activate=true to search AND activate in one step.

**Parameters:**
- query: Keywords to search (e.g., "strands memory", "aws documentation")
- auto_activate: Set to true to automatically activate the best matching tool (RECOMMENDED)
- max_results: Number of results to return (default: 5)

**Recommended Usage (fast - one API call):**
```
tool_search(query="strands long term memory", auto_activate=true)
```

**Available deferred tools will be listed in the response.**""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords to search for tools"},
                "auto_activate": {"type": "boolean", "description": "If true, automatically activate the best matching tool", "default": True},
                "max_results": {"type": "integer", "description": "Maximum number of results to return", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file at the specified path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The path to the file to read"},
                "encoding": {"type": "string", "description": "The encoding to use", "default": "utf-8"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Creates the file if it doesn't exist, or overwrites if it does.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The path to the file to write"},
                "content": {"type": "string", "description": "The content to write"},
                "encoding": {"type": "string", "description": "The encoding to use", "default": "utf-8"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "list_directory",
        "description": "List the contents of a directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The path to the directory"},
                "show_hidden": {"type": "boolean", "description": "Whether to show hidden files", "default": False}
            },
            "required": ["path"]
        }
    },
    {
        "name": "search_files",
        "description": "Search for files matching a pattern in a directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The directory to search in"},
                "pattern": {"type": "string", "description": "The glob pattern to match"}
            },
            "required": ["path", "pattern"]
        }
    },
    {
        "name": "execute_command",
        "description": "Execute a shell command. Use run_in_background=true for long-running commands.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute"},
                "working_directory": {"type": "string", "description": "The directory to run the command in"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 300, max 600 for long tasks)", "default": 300},
                "run_in_background": {"type": "boolean", "description": "Run command in background", "default": False},
                "description": {"type": "string", "description": "Description for background task"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "get_file_info",
        "description": "Get detailed information about a file or directory.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "The path to the file or directory"}},
            "required": ["path"]
        }
    },
    {
        "name": "create_directory",
        "description": "Create a new directory.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "The path where to create the directory"}},
            "required": ["path"]
        }
    },
    {
        "name": "move_file",
        "description": "Move or rename a file or directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "The source path"},
                "destination": {"type": "string", "description": "The destination path"}
            },
            "required": ["source", "destination"]
        }
    },
    {
        "name": "delete_file",
        "description": "Delete a file or empty directory.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "The path to delete"}},
            "required": ["path"]
        }
    },
    {
        "name": "git",
        "description": "Unified Git tool for all repository operations. Supports: status, log, diff, add, commit, branch, checkout, pull, push, clone.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["status", "log", "diff", "add", "commit", "branch", "checkout", "pull", "push", "clone"], "description": "Git action to perform"},
                "path": {"type": "string", "description": "Repository path"},
                "message": {"type": "string", "description": "Commit message (for commit action)"},
                "files": {"type": "array", "items": {"type": "string"}, "description": "Files to add"},
                "target": {"type": "string", "description": "Branch/commit to checkout"},
                "url": {"type": "string", "description": "Repository URL (for clone)"},
                "branch": {"type": "string", "description": "Branch name"},
                "remote": {"type": "string", "description": "Remote name"},
                "name": {"type": "string", "description": "Branch name (for create/delete)"},
                "branch_action": {"type": "string", "enum": ["list", "create", "delete"], "description": "Branch action"},
                "max_count": {"type": "integer", "description": "Max commits for log"},
                "oneline": {"type": "boolean", "description": "One-line format for log"},
                "staged": {"type": "boolean", "description": "Show staged changes (for diff)"},
                "file": {"type": "string", "description": "Specific file for diff"},
                "create": {"type": "boolean", "description": "Create new branch (for checkout)"},
                "set_upstream": {"type": "boolean", "description": "Set upstream (for push)"}
            },
            "required": ["action"]
        }
    },
    # Browser tool removed - use MCP playwright instead
    {
        "name": "glob",
        "description": "Fast file pattern matching. Returns file paths sorted by modification time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g., '**/*.py')"},
                "path": {"type": "string", "description": "Base directory to search in"},
                "limit": {"type": "integer", "description": "Maximum number of results", "default": 100}
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "grep",
        "description": "Search for content in files using regex.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regular expression pattern"},
                "path": {"type": "string", "description": "File or directory to search in"},
                "glob": {"type": "string", "description": "Glob pattern to filter files"},
                "output_mode": {"type": "string", "enum": ["files_with_matches", "content", "count"], "description": "Output mode", "default": "files_with_matches"},
                "context_lines": {"type": "integer", "description": "Lines of context", "default": 2},
                "ignore_case": {"type": "boolean", "description": "Case-insensitive search", "default": False},
                "limit": {"type": "integer", "description": "Maximum results", "default": 50}
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "edit",
        "description": "Edit a file by replacing a specific string.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file"},
                "old_string": {"type": "string", "description": "The string to find and replace"},
                "new_string": {"type": "string", "description": "The replacement string"},
                "replace_all": {"type": "boolean", "description": "Replace all occurrences", "default": False}
            },
            "required": ["path", "old_string", "new_string"]
        }
    },
    {
        "name": "read_files",
        "description": "Read multiple files at once.",
        "input_schema": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}, "description": "Array of file paths"},
                "encoding": {"type": "string", "description": "Encoding to use", "default": "utf-8"}
            },
            "required": ["paths"]
        }
    },
    {
        "name": "get_task_status",
        "description": "Get the status and output of a background task.",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "The task ID"}},
            "required": ["task_id"]
        }
    },
    {
        "name": "list_background_tasks",
        "description": "List all background tasks and their status.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "use_skill",
        "description": "__DYNAMIC_SKILL_DESCRIPTION__",
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {"type": "string", "description": "The name of the skill"},
                "user_request": {"type": "string", "description": "The user's original request"},
                "inject_mode": {
                    "type": "string",
                    "enum": ["system", "result"],
                    "default": "system",
                    "description": "How to inject skill: 'system' (Claude Code style, inject into system prompt) or 'result' (return in tool_result)"
                }
            },
            "required": ["skill_name"]
        }
    },
    {
        "name": "manage_skill",
        "description": "Create, update, or delete a reusable skill. PROACTIVE USE: After completing a complex multi-step task (deployment, data pipeline, document generation, debugging pattern, etc.), suggest to the user: 'This procedure could be saved as a skill for reuse. Want me to install it?' If user agrees, distill the procedure into a clean, self-contained skill with step-by-step instructions. Good skills capture: prerequisites, exact steps, tool calls needed, error handling, and verification steps.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "update", "delete", "list"],
                    "description": "Action to perform"
                },
                "name": {
                    "type": "string",
                    "description": "Skill name in kebab-case (e.g. 'deploy-ecs-service'). Required for create/update/delete."
                },
                "description": {
                    "type": "string",
                    "description": "One-line description of what the skill does"
                },
                "instructions": {
                    "type": "string",
                    "description": "Full markdown instructions for the agent to follow when this skill is activated. Should be a complete, self-contained procedure."
                },
                "triggers": {
                    "type": "string",
                    "description": "Comma-separated trigger phrases that should activate this skill (e.g. 'deploy to ecs, ecs deployment')"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "skill_view",
        "description": "View the full definition of a skill (instructions, resources, triggers). Use before activating a skill when you want to inspect its contents or when the skill index description is too short to decide.",
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "The name of the skill to view"
                }
            },
            "required": ["skill_name"]
        }
    },
    {
        "name": "todo_write",
        "description": "Create or update a task list to track progress.",
        "input_schema": {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": "List of todo items",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "The task description"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "completed"], "description": "Task status"},
                            "activeForm": {"type": "string", "description": "Present tense form"}
                        },
                        "required": ["content", "status", "activeForm"]
                    }
                }
            },
            "required": ["todos"]
        }
    },
    {
        "name": "todo_read",
        "description": "Read the current task list.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "ask_user",
        "description": "Ask the user a question when you need clarification.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The question to ask"},
                "options": {
                    "type": "array",
                    "description": "List of options",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "Option label"},
                            "description": {"type": "string", "description": "Option description"}
                        },
                        "required": ["label"]
                    }
                },
                "allow_custom": {"type": "boolean", "description": "Allow custom text input", "default": True}
            },
            "required": ["question", "options"]
        }
    },
    {
        "name": "enter_plan_mode",
        "description": "Enter plan mode to design an implementation approach before making changes.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "Why you're entering plan mode"}},
            "required": ["reason"]
        }
    },
    {
        "name": "exit_plan_mode",
        "description": "Exit plan mode and present the plan to the user for approval.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plan_summary": {"type": "string", "description": "Summary of the plan"},
                "steps": {"type": "array", "items": {"type": "string"}, "description": "List of steps"},
                "files_to_modify": {"type": "array", "items": {"type": "string"}, "description": "Files to modify"}
            },
            "required": ["plan_summary", "steps"]
        }
    },
    {
        "name": "summarize_context",
        "description": "Summarize the current conversation context.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "A concise summary"},
                "key_decisions": {"type": "array", "items": {"type": "string"}, "description": "Important decisions"},
                "pending_tasks": {"type": "array", "items": {"type": "string"}, "description": "Pending tasks"}
            },
            "required": ["summary"]
        }
    },
    {
        "name": "task",
        "description": "Launch a background agent for complex, multi-step tasks. Use this when: (1) Deep codebase exploration requiring many file reads, (2) Tasks that may take >30 seconds, (3) Research requiring multiple iterations, (4) Parallel independent subtasks. Agent types: 'explore' for code analysis, 'research' for web/info gathering, 'implement' for code changes, 'general' for other tasks. The task runs asynchronously and results are returned when complete.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Short task description (3-5 words)"},
                "prompt": {"type": "string", "description": "Detailed instructions for the agent"},
                "agent_type": {"type": "string", "enum": ["explore", "research", "implement", "general"], "description": "Type of specialized agent to use", "default": "general"},
                "run_in_background": {"type": "boolean", "description": "Run in background (default: true)", "default": True}
            },
            "required": ["description", "prompt"]
        }
    },
    {
        "name": "delegate_task",
        "description": "Delegate a task to another session for execution.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_number": {"type": "integer", "description": "The session number to delegate to"},
                "task": {"type": "string", "description": "The task description"},
                "create_new_session": {"type": "boolean", "description": "Create a new session", "default": False},
                "working_directory": {"type": "string", "description": "Working directory for new session"},
                "session_name": {"type": "string", "description": "Name for the new session"},
                "wait_for_result": {"type": "boolean", "description": "Wait for task to complete", "default": False}
            },
            "required": ["task"]
        }
    },
    {
        "name": "scheduler",
        "description": """Create scheduled or delayed tasks.

**CRITICAL: For repeated reminders, create exactly ONE cron task. NEVER call this tool multiple times.**

When user says "每N分钟提醒我X，共Y次":
- Call scheduler ONCE with: schedule_type="cron", schedule_value="*/N * * * *", max_executions=Y
- DO NOT create Y separate tasks!

Cron format: "minute hour day month weekday"
- "*/2 * * * *" = every 2 minutes
- "*/30 * * * *" = every 30 minutes
- "0 * * * *" = every hour
- "0 9 * * *" = daily 9am

**Required examples:**
- "每2分钟提醒喝水，共3次" → ONE call: schedule_type="cron", schedule_value="*/2 * * * *", max_executions=3
- "每小时提醒休息，到18点" → ONE call: schedule_type="cron", schedule_value="0 * * * *", end_date="2026-02-06T18:00:00"
- "30分钟后提醒" → schedule_type="delay", schedule_value="30"
- "明天3点" → schedule_type="once", schedule_value="2026-02-07T15:00:00" """,
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "cancel", "update", "pause", "resume"],
                    "description": "Action to perform. pause/resume temporarily stops/restarts a task without deleting it."
                },
                "name": {
                    "type": "string",
                    "description": "Task name/description"
                },
                "schedule_type": {
                    "type": "string",
                    "enum": ["cron", "delay", "once"],
                    "description": "cron=recurring, delay=after N minutes, once=at specific time"
                },
                "schedule_value": {
                    "type": "string",
                    "description": "Cron expression (e.g., '0 9 * * *'), minutes to delay (e.g., '30'), or ISO datetime (e.g., '2026-02-06T15:00:00')"
                },
                "prompt": {
                    "type": "string",
                    "description": "The prompt/task to execute when triggered"
                },
                "task_id": {
                    "type": "string",
                    "description": "Task ID for cancel/update actions"
                },
                "enabled": {
                    "type": "boolean",
                    "description": "Whether task is enabled (for update)",
                    "default": True
                },
                "notify_on_trigger": {
                    "type": "boolean",
                    "description": "Show notification when task triggers",
                    "default": True
                },
                "create_session": {
                    "type": "boolean",
                    "description": "Create new session for task execution",
                    "default": True
                },
                "working_directory": {
                    "type": "string",
                    "description": "Working directory for task execution. If not specified, inherits from current session."
                },
                "max_executions": {
                    "type": "integer",
                    "description": "Maximum number of executions for cron tasks. Task stops after reaching this count."
                },
                "end_date": {
                    "type": "string",
                    "description": "End date for cron tasks (ISO format, e.g., '2026-02-10T18:00:00'). Task stops after this date."
                }
            },
            "required": ["action"]
        }
    },

    # ============ Computer Use Tool ============
    {
        "name": "computer",
        "description": """Control the computer screen, mouse, and keyboard. Take screenshots to see what's on screen, click elements, type text, scroll, and perform other GUI interactions.

**Multi-display:** Use list_displays to see all monitors, switch_display to target a specific one. After switching, all actions target that display.

**Important guidelines:**
- Always take a screenshot first to see what's on screen before acting.
- If a floating toolbar or overlay is blocking the target, tell the user to close it manually rather than repeatedly trying to dismiss it.
- Do NOT loop more than 2-3 times on the same failed action. If stuck, explain the problem and ask the user for help.
- Coordinates are relative to the active display's screenshot. Use list_displays if unsure which display is active.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "screenshot", "left_click", "right_click", "middle_click",
                        "double_click", "triple_click", "mouse_move",
                        "left_click_drag", "key", "type", "scroll",
                        "cursor_position", "wait",
                        "list_displays", "switch_display"
                    ],
                    "description": "The action to perform. Use list_displays to see all monitors, switch_display to target a specific one."
                },
                "coordinate": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "[x, y] position for click/move actions"
                },
                "text": {
                    "type": "string",
                    "description": "Text to type (for 'type') or key combo (for 'key', e.g. 'ctrl+c')"
                },
                "duration": {
                    "type": "integer",
                    "description": "Duration in seconds (for 'wait' action)"
                },
                "scroll_direction": {
                    "type": "string",
                    "enum": ["up", "down", "left", "right"],
                    "description": "Scroll direction"
                },
                "scroll_amount": {
                    "type": "integer",
                    "description": "Number of scroll steps (default 3)"
                },
                "start_coordinate": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "[x, y] start position for drag"
                },
                "display": {
                    "type": "integer",
                    "description": "Target display index (1-based). Sets active display for this and subsequent calls. Use list_displays to see available monitors."
                }
            },
            "required": ["action"]
        },
        # Marker for Bedrock integration: transform to computer_20250124 beta format
        "_bedrock_tool_type": "computer_20250124",
    },
    # ============ LSP (Language Server Protocol) Tools ============
    {
        "name": "lsp_go_to_definition",
        "description": "Find where a symbol is defined using LSP code intelligence. Provide the file path and the position (1-based line and character) of the symbol. Returns the file and position of the definition. Requires a language server (pylsp for Python, typescript-language-server for TS/JS).",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the source file"},
                "line": {"type": "integer", "description": "Line number (1-based)"},
                "character": {"type": "integer", "description": "Character offset on the line (1-based)"},
                "workspace_root": {"type": "string", "description": "Optional workspace root directory. Auto-detected if not provided."}
            },
            "required": ["file_path", "line", "character"]
        }
    },
    {
        "name": "lsp_find_references",
        "description": "Find all references to a symbol across the codebase using LSP. Returns a list of locations where the symbol is used. Useful for understanding impact of changes or finding all callers of a function.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the source file"},
                "line": {"type": "integer", "description": "Line number (1-based)"},
                "character": {"type": "integer", "description": "Character offset on the line (1-based)"},
                "include_declaration": {"type": "boolean", "description": "Include the declaration itself in results", "default": True},
                "workspace_root": {"type": "string", "description": "Optional workspace root directory"}
            },
            "required": ["file_path", "line", "character"]
        }
    },
    {
        "name": "lsp_hover",
        "description": "Get type information and documentation for a symbol at a given position. Returns hover content (type signature, docstring) from the language server.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the source file"},
                "line": {"type": "integer", "description": "Line number (1-based)"},
                "character": {"type": "integer", "description": "Character offset on the line (1-based)"},
                "workspace_root": {"type": "string", "description": "Optional workspace root directory"}
            },
            "required": ["file_path", "line", "character"]
        }
    },
    {
        "name": "lsp_document_symbols",
        "description": "Get all symbols (functions, classes, variables, methods) defined in a file. Useful for understanding file structure without reading the entire file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the source file"},
                "workspace_root": {"type": "string", "description": "Optional workspace root directory"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "lsp_workspace_symbol",
        "description": "Search for symbols (functions, classes, etc.) across the entire workspace by name. Useful for finding where something is defined when you only know its name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Symbol name or partial name to search for"},
                "file_path": {"type": "string", "description": "A file in the workspace (used to identify the workspace and language)"},
                "workspace_root": {"type": "string", "description": "Optional workspace root directory"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "lsp_diagnostics",
        "description": "Get errors and warnings for a file from the language server. Returns diagnostic messages with severity, line number, and description.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the source file"},
                "workspace_root": {"type": "string", "description": "Optional workspace root directory"}
            },
            "required": ["file_path"]
        }
    },
    # ============ Memory Tools ============
    {
        "name": "memory_search",
        "description": """Search your persistent memory across local memory files and long-term AgentCore storage.

**Scopes:**
- `recent`: Search memory/*.md files (within retention window, default 7 days) — fast, local grep
- `longterm`: Search AgentCore Memory (older than retention window) — slower, semantic search
- `auto` (default): Search recent first, then longterm if not enough results
- `list`: List all local memory files with metadata (ignores query)

**When to use this tool:**
- Before answering questions about prior conversations, decisions, preferences, or context from previous sessions
- When the user references something discussed "before", "last time", "yesterday", etc.
- When you need to recall stored facts, todos, or project context
- When you want to see what memory files exist: use scope="list"

Memory files are stored at `~/.springo/workspace/memory/`. **NEVER** use list_directory, glob, or read_file to browse memory directories — always use this tool or memory_get.

Note: MEMORY.md and the last 2 days of daily logs are already injected into your system prompt. Use this tool for searching **older** memory files or when you need targeted recall.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query text (ignored when scope='list')"},
                "scope": {
                    "type": "string",
                    "description": "Search scope: 'auto' (default), 'recent' (local files only), 'longterm' (AgentCore only), 'list' (list all memory files)",
                    "enum": ["auto", "recent", "longterm", "list"],
                    "default": "auto"
                },
                "max_results": {"type": "integer", "description": "Maximum results to return (default: 10)", "default": 10},
                "days": {"type": "integer", "description": "Override retention days for recent search"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "memory_write",
        "description": """Write content to your persistent memory files.

**Targets:**
- `daily`: Append a note to today's daily log (`memory/YYYY-MM-DD.md`). Use for session-specific observations, decisions, todos, running context.
- `longterm`: Append to MEMORY.md (curated long-term memory). Use for durable facts, user preferences, project decisions that should persist across all sessions.

**When to use this tool:**
- When the user says "remember this", "note that", "don't forget"
- When you discover important preferences, decisions, or facts worth preserving
- When you make a significant decision or complete a key task — record it
- Before context compaction, to save critical information that shouldn't be lost
- To record project conventions, architecture decisions, recurring patterns

**Guidelines:**
- Write concise, structured Markdown (use headers, bullets)
- Daily log entries are append-only (new content added to end)
- MEMORY.md appends are added to the existing content (not overwritten)
- Prefer daily log for transient notes; MEMORY.md for durable facts
- Do NOT store raw conversation transcripts — store distilled insights""",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Where to write: 'daily' (today's log) or 'longterm' (MEMORY.md)",
                    "enum": ["daily", "longterm"]
                },
                "content": {
                    "type": "string",
                    "description": "Markdown content to write"
                }
            },
            "required": ["target", "content"]
        }
    },
    {
        "name": "memory_get",
        "description": """Read a specific memory file by path. Use after memory_search to read full content of a matched file.

Base path: `~/.springo/workspace/`. Pass relative paths like 'MEMORY.md' or 'memory/2026-02-26.md'.
**NEVER** use read_file or execute_command to read memory files — always use this tool.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path within workspace (e.g., 'MEMORY.md', 'memory/2026-02-26.md')"},
                "from_line": {"type": "integer", "description": "Start reading from this line (1-based)"},
                "lines": {"type": "integer", "description": "Number of lines to read"}
            },
            "required": ["path"]
        }
    },
    # ──────── ACP Agent Tools ────────
    {
        "name": "acp_prompt",
        "description": """Delegate a task to an external ACP-compatible AI agent (Kiro, Gemini, Cline, OpenClaw, etc.).

Each ACP agent uses its own LLM/subscription. Use this to:
- Get a second opinion from another AI
- Leverage specialized agents for specific tasks
- Delegate sub-tasks to agents with different capabilities

Supports stateful multi-turn conversations: pass session_id from a previous call or from acp_new_session to keep context across turns. Omit session_id for stateless one-shot calls.

Available agents are configured in ~/.springo/acp_agents.json.
Use acp_list_agents first to see what's available.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent": {"type": "string", "description": "Name of the ACP agent (e.g., 'kiro', 'gemini')"},
                "prompt": {"type": "string", "description": "The task/prompt to send to the agent"},
                "cwd": {"type": "string", "description": "Working directory for the agent session", "default": "/tmp"},
                "timeout": {"type": "number", "description": "Max seconds to wait for response", "default": 600},
                "session_id": {"type": "string", "description": "Session ID to reuse for multi-turn context. Get from acp_new_session or a previous acp_prompt response."}
            },
            "required": ["agent", "prompt"]
        }
    },
    {
        "name": "acp_list_agents",
        "description": "List all configured ACP agents and their status (running, enabled, capabilities).",
        "input_schema": {
            "type": "object",
            "properties": {},
        }
    },
    {
        "name": "acp_new_session",
        "description": """Create a persistent session on an ACP agent for stateful multi-turn conversations.

Returns a session_id that can be passed to subsequent acp_prompt calls to maintain context.
Use this when you need the agent to remember previous conversation turns.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent": {"type": "string", "description": "Name of the ACP agent"},
                "cwd": {"type": "string", "description": "Working directory for the session", "default": "/tmp"}
            },
            "required": ["agent"]
        }
    },
    {
        "name": "canvas",
        "description": (
            "READ-ONLY inspection of Springo's Canvas panel. Every call returns synchronously.\n\n"
            "Actions:\n"
            "- list: list all open/pinned artifacts → [{id, name, type, pinned, fileCount, isActive}]\n"
            "- read: read the source of an artifact. If `path` is given, returns that file's content; otherwise returns all files.\n"
            "- state: return the latest runtime state the artifact reported via window.springo.setState(...).\n"
            "- query: evaluate a CSS selector against the live iframe and return {exists, text, tagName, classes}.\n\n"
            "To CREATE, PATCH, or DRIVE an artifact, emit a <springo-artifact op=\"create|patch|action\"> "
            "XML tag directly in your response text. That is the only write path; this tool cannot mutate Canvas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "read", "state", "query"],
                    "description": "What to read from Canvas",
                },
                "artifact_id": {
                    "type": "string",
                    "description": "Target artifact id (read from <artifact-context> or canvas(action='list')). Required for all actions except 'list'.",
                },
                "path": {
                    "type": "string",
                    "description": "For action='read': which file to read. Omit to read all files.",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector inside the iframe. Required for 'query'.",
                },
                "timeout": {
                    "type": "number",
                    "description": "Max seconds to wait for the renderer. Default 15.",
                    "default": 15,
                },
            },
            "required": ["action"],
        },
    },
    # ──────── Knowledge Base Tools ────────
    {
        "name": "kb_list",
        "description": """List wiki pages in the local knowledge base.

The KB lives at `~/.springo/kb/` and follows the schema in CLAUDE.md
(every page has frontmatter + summary + key claims with source pointers).

scope:
- 'all' (default) — all pages
- 'orphans' — pages with no inbound `[[link]]`s
- 'stale' — pages whose `last_updated` is > 180 days

Returns: { ok, pages: [{slug, title, tags, claim_count, source_count, orphan, stale, last_updated}], stats }""",
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["all", "orphans", "stale"], "default": "all"},
            },
        },
    },
    {
        "name": "kb_search",
        "description": """Plain-text grep across KB wiki pages. No vector index, no chunks — exactly per the design (CLAUDE.md "Storage substrate"). Use this to find relevant pages, then call kb_read_page on the matches you want to read in full.

Returns: { ok, results: [{slug, title, tags, snippet}], total }""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search text. Case-insensitive substring match."},
                "max_results": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "kb_read_page",
        "description": """Read one wiki page by slug. Always read the full page — don't try to chunk. The body is markdown with the schema's standard sections (Summary / Key claims / Open questions / See also).""",
        "input_schema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "The page slug (kebab-case, matches filename without .md)"},
            },
            "required": ["slug"],
        },
    },
    {
        "name": "kb_write_page",
        "description": """Create or replace a wiki page. The content MUST start with the schema's frontmatter (see ~/.springo/kb/CLAUDE.md). Required fields: title, slug, tags, sources, created_at, last_updated. Body sections: Summary, Key claims (each fact ends with a source pointer), Open questions, See also (with [[other-slug]] links).

If you're updating an existing page, kb_read_page it first, edit the body, write the whole thing back. Don't replace `sources:` — append.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string"},
                "content": {"type": "string", "description": "Full markdown including frontmatter."},
            },
            "required": ["slug", "content"],
        },
    },
    {
        "name": "kb_ingest_text",
        "description": """Ingest a text snippet (pasted content, extracted webpage, email body) into ~/.springo/kb/raw/ as a markdown file. Always tier=full because it's small.

Returns the raw_path which you should reference in the wiki page's `sources:` list. Typical flow: kb_ingest_text → kb_write_page (with raw_path in frontmatter sources).""",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short title — used in the raw filename"},
                "content": {"type": "string", "description": "The text to ingest"},
                "source_url": {"type": "string", "description": "Optional original URL"},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "kb_ingest_file",
        "description": """Ingest a file from disk into ~/.springo/kb/raw/. Tier is auto-decided by size:
- < 50 MB → full (file copied)
- 50 MB – 1 GB → returns a plan; user must confirm before commit
- > 1 GB → REFUSED (use kb_ingest_external or extract a transcript and call kb_ingest_text)

Returns { ok, committed, raw_path, sha256, size_bytes } on success, or { ok, needs_user_confirmation: true, plan } when the file is between 50 MB and 1 GB.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_path": {"type": "string", "description": "Absolute or expandable path"},
                "slug_hint": {"type": "string", "description": "Optional kebab-case slug for the raw filename"},
            },
            "required": ["source_path"],
        },
    },
    {
        "name": "kb_ingest_pdf",
        "description": """Ingest a PDF: copies the file into raw/ AND returns extracted text in one call so you can immediately distill it into wiki pages without a second tool round-trip.

Returns { ok, committed, raw_path, page_count, text_excerpt, text_truncated, text_length, next_step }. The text_excerpt is capped at 50000 chars; if truncated, read the full file from raw_path with read_file. Then call kb_write_page once per topic with the raw_path as your source pointer.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_path": {"type": "string"},
                "slug_hint": {"type": "string"},
            },
            "required": ["source_path"],
        },
    },
    {
        "name": "kb_lint",
        "description": """Run the KB lint pass: find orphan pages (no inbound links), stale pages (last_updated > 180 days), missing tags, pages with no sources, dead source files, and schema drift. Read-only — never deletes or rewrites. Use to find what to clean up, then apply fixes via kb_write_page.""",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "kb_stats",
        "description": """Top-level KB metrics: page_count, edge_count, orphan_count, stale_count, raw_count, raw_total_bytes. Cheap.""",
        "input_schema": {"type": "object", "properties": {}},
    },
    # ── Browser extension tools (drive the user's REAL Chrome) ──────────────
    # These run inside the user's signed-in Chrome via the Springo extension,
    # so authenticated pages work. Requires the extension to be installed and
    # connected — check web_browser_status first if a call reports "not connected".
    {
        "name": "web_browser_status",
        "description": "Check whether the Springo Chrome extension is connected. Call this first if browser tools report the extension is not connected. Returns { connected, client, pending }.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "web_navigate",
        "description": "Navigate the controlled Chrome tab to a URL. Runs in the user's real, signed-in Chrome inside a dedicated 'Springo' tab group — so logged-in sites work without re-auth.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Absolute URL to open (include https://)"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "web_click",
        "description": "Click an element in the controlled tab. Provide a CSS `selector`, or both `x` and `y` viewport coordinates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector of the element to click"},
                "x": {"type": "number", "description": "Viewport X coordinate (alternative to selector)"},
                "y": {"type": "number", "description": "Viewport Y coordinate (alternative to selector)"},
            },
        },
    },
    {
        "name": "web_type",
        "description": "Type text into the focused field, or into the element matched by `selector`. Set submit=true to press Enter after typing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type"},
                "selector": {"type": "string", "description": "Optional CSS selector to focus first"},
                "submit": {"type": "boolean", "description": "Press Enter after typing", "default": False},
            },
            "required": ["text"],
        },
    },
    {
        "name": "web_read_page",
        "description": "Read the current page content from the controlled tab. format: 'text' (visible text, default) or 'html' (full HTML).",
        "input_schema": {
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": ["text", "html"], "default": "text"},
            },
        },
    },
    {
        "name": "web_screenshot",
        "description": "Capture a PNG screenshot of the controlled Chrome tab. Returns base64 image data. Set full_page=true for the entire scrollable page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "full_page": {"type": "boolean", "description": "Capture the full scrollable page", "default": False},
            },
        },
    },
    {
        "name": "web_evaluate",
        "description": "Evaluate a JavaScript expression in the controlled page and return its result. Use for extracting structured data or checking page state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "JavaScript expression to evaluate in the page"},
            },
            "required": ["expression"],
        },
    },
    {
        "name": "web_tabs",
        "description": "Manage tabs within Springo's tab group. action: 'list' (default), 'open' (needs url), 'close' (needs index), 'select' (needs index).",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "open", "close", "select"], "default": "list"},
                "url": {"type": "string", "description": "URL to open (action=open)"},
                "index": {"type": "integer", "description": "Tab index within the group (action=close/select)"},
            },
        },
    },
]
