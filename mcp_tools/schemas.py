"""
Tool Definitions Schema
JSON schemas for all MCP tools sent to Claude
"""

TOOL_DEFINITIONS = [
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
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
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
        "description": "Launch a specialized sub-task for complex operations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Short task description"},
                "prompt": {"type": "string", "description": "Detailed instructions"},
                "agent_type": {"type": "string", "enum": ["explore", "research", "implement", "general"], "description": "Agent type", "default": "general"},
                "run_in_background": {"type": "boolean", "description": "Run in background", "default": False}
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
    }
]
