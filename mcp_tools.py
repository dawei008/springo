"""
MCP Tools Implementation for Springo
Provides file system, terminal, git, web search, browser automation and other cowork functionality
"""

import os
import subprocess
import json
import base64
import glob as glob_module
import mimetypes
import asyncio
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# Skill loader import
try:
    from skill_loader import get_skill_loader
    HAS_SKILL_LOADER = True
except ImportError:
    HAS_SKILL_LOADER = False

# Optional imports with graceful fallback
try:
    import requests
    from bs4 import BeautifulSoup
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# Browser singleton for Playwright
_browser_manager = None

# Working directory configuration (set by user from UI)
_working_dir = ""

def set_working_dir(path: str):
    """Set the current working directory for tool operations"""
    global _working_dir
    _working_dir = os.path.abspath(os.path.expanduser(path)) if path else ""

def get_working_dir() -> str:
    """Get the current working directory"""
    return _working_dir

def resolve_path(path: str = None, default_to_working_dir: bool = True) -> str:
    """Resolve path, using working directory as default if set"""
    if path:
        # If path is relative and working dir is set, resolve relative to working dir
        if not os.path.isabs(path) and _working_dir:
            return os.path.abspath(os.path.join(_working_dir, path))
        return os.path.abspath(os.path.expanduser(path))
    elif default_to_working_dir and _working_dir:
        return _working_dir
    else:
        return os.getcwd()

# Safety: Define allowed directories for READ operations (broader access for skills, system files)
ALLOWED_READ_DIRECTORIES = [
    "/",  # Allow reading from anywhere (for skills, system files, etc.)
]

# Safety: Define allowed directories for WRITE operations (more restrictive)
# Writing is restricted to user home; working_dir further restricts output location
ALLOWED_WRITE_DIRECTORIES = [
    os.path.expanduser("~"),  # User home only for writes
    "/tmp",  # Temp directory allowed for writes
]

# Safety: Commands that are blocked
BLOCKED_COMMANDS = [
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=", ":(){:|:&};:",
    "chmod -R 777 /", "chown -R", "> /dev/sda",
]

def is_path_allowed_for_read(path: str) -> bool:
    """Check if path is allowed for read operations (broader access)"""
    abs_path = os.path.abspath(os.path.expanduser(path))
    for allowed in ALLOWED_READ_DIRECTORIES:
        if abs_path.startswith(os.path.abspath(allowed)):
            return True
    return False

def is_path_allowed_for_write(path: str) -> bool:
    """Check if path is allowed for write operations (more restrictive)"""
    abs_path = os.path.abspath(os.path.expanduser(path))
    for allowed in ALLOWED_WRITE_DIRECTORIES:
        if abs_path.startswith(os.path.abspath(allowed)):
            return True
    return False

def is_path_allowed(path: str, for_write: bool = False) -> bool:
    """Check if path is within allowed directories"""
    if for_write:
        return is_path_allowed_for_write(path)
    return is_path_allowed_for_read(path)

def is_command_safe(command: str) -> bool:
    """Check if command is safe to execute"""
    cmd_lower = command.lower().strip()
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return False
    return True


# =============================================================================
# Tool Definitions (sent to Claude)
# =============================================================================

TOOL_DEFINITIONS = [
    {
        "name": "tool_search",
        "description": """Search for or select deferred tools to make them available for use.

**MANDATORY PREREQUISITE** - You MUST use this tool to load deferred MCP tools BEFORE calling them.

**Query modes:**

1. **Direct selection** - Use `select:<tool_name>` when you know which tool you need:
   - "select:context7__query-docs"
   - Returns and activates that specific tool

2. **Keyword search** - Use keywords when unsure which tool to use:
   - "react documentation" - find tools for React docs
   - "library search" - find library search tools
   - Returns up to 5 matching tools ranked by relevance

**CORRECT Usage Pattern:**
1. Search or select a tool using this tool
2. If the tool is "deferred", it will be activated automatically
3. Then call the activated tool

**Example:**
User: "How do I use React hooks?"
Assistant: [Calls tool_search with query: "select:context7__resolve-library-id"]
[Tool is activated]
Assistant: [Now can call context7__resolve-library-id]

**Available deferred tools will be listed in the response.**""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Query to find tools. Use 'select:<tool_name>' for direct selection, or keywords to search."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file at the specified path. Use this to examine files on the user's system.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The absolute or relative path to the file to read"
                },
                "encoding": {
                    "type": "string",
                    "description": "The encoding to use (default: utf-8)",
                    "default": "utf-8"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write content to a file at the specified path. Creates the file if it doesn't exist, or overwrites if it does. IMPORTANT: For large files (>100 lines), consider writing incrementally or creating smaller helper files. Always include the 'content' parameter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The absolute or relative path to the file to write"
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file"
                },
                "encoding": {
                    "type": "string",
                    "description": "The encoding to use (default: utf-8)",
                    "default": "utf-8"
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "list_directory",
        "description": "List the contents of a directory. Returns file names, types, and sizes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the directory to list"
                },
                "show_hidden": {
                    "type": "boolean",
                    "description": "Whether to show hidden files (default: false)",
                    "default": False
                }
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
                "path": {
                    "type": "string",
                    "description": "The directory to search in"
                },
                "pattern": {
                    "type": "string",
                    "description": "The glob pattern to match (e.g., '*.py', '**/*.js')"
                }
            },
            "required": ["path", "pattern"]
        }
    },
    {
        "name": "execute_command",
        "description": "Execute a shell command. Supports both synchronous and background execution. Use run_in_background=true for long-running commands like builds, tests, or servers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute"
                },
                "working_directory": {
                    "type": "string",
                    "description": "The directory to run the command in (default: current directory)"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 60, ignored for background tasks)",
                    "default": 60
                },
                "run_in_background": {
                    "type": "boolean",
                    "description": "Run command in background. Returns task_id for tracking progress.",
                    "default": False
                },
                "description": {
                    "type": "string",
                    "description": "Description for background task (helps with task tracking)"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "get_file_info",
        "description": "Get detailed information about a file or directory (size, permissions, modification time, etc.)",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the file or directory"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "create_directory",
        "description": "Create a new directory at the specified path. Creates parent directories if needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path where to create the directory"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "move_file",
        "description": "Move or rename a file or directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "The source path"
                },
                "destination": {
                    "type": "string",
                    "description": "The destination path"
                }
            },
            "required": ["source", "destination"]
        }
    },
    {
        "name": "delete_file",
        "description": "Delete a file or empty directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the file or directory to delete"
                }
            },
            "required": ["path"]
        }
    },
    # =============================================================================
    # Git Tool (Unified - Claude Code pattern)
    # =============================================================================
    {
        "name": "git",
        "description": "Unified Git tool for all repository operations. Supports: status, log, diff, add, commit, branch, checkout, pull, push, clone.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "log", "diff", "add", "commit", "branch", "checkout", "pull", "push", "clone"],
                    "description": "Git action to perform"
                },
                "path": {
                    "type": "string",
                    "description": "Repository path (default: working directory)"
                },
                "message": {
                    "type": "string",
                    "description": "Commit message (for commit action)"
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files to add (for add action, use ['.'] for all)"
                },
                "target": {
                    "type": "string",
                    "description": "Branch/commit to checkout (for checkout action)"
                },
                "url": {
                    "type": "string",
                    "description": "Repository URL (for clone action)"
                },
                "branch": {
                    "type": "string",
                    "description": "Branch name (for various actions)"
                },
                "remote": {
                    "type": "string",
                    "description": "Remote name (default: origin)"
                },
                "name": {
                    "type": "string",
                    "description": "Branch name (for branch create/delete)"
                },
                "branch_action": {
                    "type": "string",
                    "enum": ["list", "create", "delete"],
                    "description": "Branch action (for branch action)"
                },
                "max_count": {
                    "type": "integer",
                    "description": "Max commits for log (default: 10)"
                },
                "oneline": {
                    "type": "boolean",
                    "description": "One-line format for log"
                },
                "staged": {
                    "type": "boolean",
                    "description": "Show staged changes (for diff)"
                },
                "file": {
                    "type": "string",
                    "description": "Specific file for diff"
                },
                "create": {
                    "type": "boolean",
                    "description": "Create new branch (for checkout)"
                },
                "set_upstream": {
                    "type": "boolean",
                    "description": "Set upstream (for push)"
                }
            },
            "required": ["action"]
        }
    },
    # =============================================================================
    # Web Search Tools
    # =============================================================================
    {
        "name": "web_search",
        "description": "Search the web using configured search engine (Brave, Tavily, or Custom API).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 10)",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "web_fetch",
        "description": "Fetch the content of a web page and return the text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL of the web page to fetch"
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector to extract specific content (optional)"
                }
            },
            "required": ["url"]
        }
    },
    # =============================================================================
    # Browser Tool (Unified - Claude Code pattern)
    # =============================================================================
    {
        "name": "browser",
        "description": "Unified Browser automation tool (Playwright). Supports: navigate, screenshot, click, type, get_text, evaluate, close.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["navigate", "screenshot", "click", "type", "get_text", "evaluate", "close"],
                    "description": "Browser action to perform"
                },
                "url": {
                    "type": "string",
                    "description": "URL to navigate to (for navigate action)"
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector for element (for click, type, screenshot, get_text)"
                },
                "text": {
                    "type": "string",
                    "description": "Text to type (for type action)"
                },
                "script": {
                    "type": "string",
                    "description": "JavaScript to execute (for evaluate action)"
                },
                "wait_until": {
                    "type": "string",
                    "enum": ["load", "domcontentloaded", "networkidle"],
                    "description": "Wait condition for navigate (default: load)"
                },
                "full_page": {
                    "type": "boolean",
                    "description": "Full page screenshot (for screenshot action)"
                },
                "clear": {
                    "type": "boolean",
                    "description": "Clear input before typing (default: true)"
                }
            },
            "required": ["action"]
        }
    },
    # =============================================================================
    # Optimized Tools (Claude Code patterns)
    # =============================================================================
    {
        "name": "glob",
        "description": "Fast file pattern matching. Use this instead of find or ls commands. Returns file paths sorted by modification time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g., '**/*.py', 'src/**/*.ts', '*.md')"
                },
                "path": {
                    "type": "string",
                    "description": "Base directory to search in (default: working directory)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 100)",
                    "default": 100
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "grep",
        "description": "Search for content in files using regex. Use this instead of grep/rg bash commands. Supports output modes: 'files_with_matches' (default, fast), 'content' (shows matching lines), 'count' (match counts).",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regular expression pattern to search for"
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search in (default: working directory)"
                },
                "glob": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g., '*.py', '*.{js,ts}')"
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["files_with_matches", "content", "count"],
                    "description": "Output mode: files_with_matches (just paths), content (matching lines with context), count (match counts)",
                    "default": "files_with_matches"
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Lines of context before/after match (for content mode)",
                    "default": 2
                },
                "ignore_case": {
                    "type": "boolean",
                    "description": "Case-insensitive search",
                    "default": False
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default: 50)",
                    "default": 50
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "edit",
        "description": "Edit a file by replacing a specific string. More precise than write_file for modifications. The old_string must be unique in the file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit"
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact string to find and replace (must be unique in file)"
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement string"
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences instead of just first (default: false)",
                    "default": False
                }
            },
            "required": ["path", "old_string", "new_string"]
        }
    },
    {
        "name": "read_files",
        "description": "Read multiple files at once. More efficient than multiple read_file calls for related files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Array of file paths to read"
                },
                "encoding": {
                    "type": "string",
                    "description": "Encoding to use (default: utf-8)",
                    "default": "utf-8"
                }
            },
            "required": ["paths"]
        }
    },
    {
        "name": "get_task_status",
        "description": "Get the status and output of a background task started with execute_command(run_in_background=true)",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID returned by execute_command"
                }
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "list_background_tasks",
        "description": "List all background tasks and their current status",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "use_skill",
        "description": "__DYNAMIC_SKILL_DESCRIPTION__",  # Placeholder - will be replaced dynamically
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "The name of the skill to use"
                },
                "user_request": {
                    "type": "string",
                    "description": "The user's original request that triggered this skill"
                }
            },
            "required": ["skill_name"]
        }
    },
    # =============================================================================
    # P0: Todo Task Tracking System (Claude Code pattern)
    # =============================================================================
    {
        "name": "todo_write",
        "description": "Create or update a task list to track progress on complex tasks. Use this to break down tasks and show progress to the user. Each todo has content (what to do), status (pending/in_progress/completed), and activeForm (present tense description shown during execution).",
        "input_schema": {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": "List of todo items",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "The task description (imperative form, e.g., 'Fix the bug')"
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                                "description": "Task status"
                            },
                            "activeForm": {
                                "type": "string",
                                "description": "Present tense form (e.g., 'Fixing the bug')"
                            }
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
        "description": "Read the current task list to check progress",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    # =============================================================================
    # P1: User Question Mechanism (Claude Code pattern)
    # =============================================================================
    {
        "name": "ask_user",
        "description": "Ask the user a question when you need clarification, want to validate assumptions, or need to make a decision. Present clear options for the user to choose from.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user"
                },
                "options": {
                    "type": "array",
                    "description": "List of options for the user to choose from",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "Short label for the option"
                            },
                            "description": {
                                "type": "string",
                                "description": "Explanation of what this option means"
                            }
                        },
                        "required": ["label"]
                    }
                },
                "allow_custom": {
                    "type": "boolean",
                    "description": "Allow user to provide custom text input (default: true)",
                    "default": True
                }
            },
            "required": ["question", "options"]
        }
    },
    # =============================================================================
    # P2: Plan Mode (Claude Code pattern)
    # =============================================================================
    {
        "name": "enter_plan_mode",
        "description": "Enter plan mode to design an implementation approach before making changes. In plan mode, focus on exploration and planning without modifying files. Use this for complex tasks that need careful design.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why you're entering plan mode"
                }
            },
            "required": ["reason"]
        }
    },
    {
        "name": "exit_plan_mode",
        "description": "Exit plan mode and present the plan to the user for approval. Include a summary of what will be done.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plan_summary": {
                    "type": "string",
                    "description": "Summary of the planned implementation"
                },
                "steps": {
                    "type": "array",
                    "description": "List of steps to be executed",
                    "items": {
                        "type": "string"
                    }
                },
                "files_to_modify": {
                    "type": "array",
                    "description": "List of files that will be created or modified",
                    "items": {
                        "type": "string"
                    }
                }
            },
            "required": ["plan_summary", "steps"]
        }
    },
    # =============================================================================
    # P2: Context Summarization (Claude Code pattern)
    # =============================================================================
    {
        "name": "summarize_context",
        "description": "Summarize the current conversation context when it gets too long. This helps maintain context while reducing token usage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "A concise summary of the conversation so far"
                },
                "key_decisions": {
                    "type": "array",
                    "description": "Important decisions made during the conversation",
                    "items": {
                        "type": "string"
                    }
                },
                "pending_tasks": {
                    "type": "array",
                    "description": "Tasks that are still pending",
                    "items": {
                        "type": "string"
                    }
                }
            },
            "required": ["summary"]
        }
    },
    # =============================================================================
    # P3: Specialized Agent Task (Claude Code pattern)
    # =============================================================================
    {
        "name": "task",
        "description": "Launch a specialized sub-task for complex operations. Use this when a task requires focused work that benefits from isolation. Available agent types: 'explore' (code exploration), 'research' (web research), 'implement' (code implementation).",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Short description of the task (3-5 words)"
                },
                "prompt": {
                    "type": "string",
                    "description": "Detailed instructions for the task"
                },
                "agent_type": {
                    "type": "string",
                    "enum": ["explore", "research", "implement", "general"],
                    "description": "Type of agent to use (default: general)",
                    "default": "general"
                },
                "run_in_background": {
                    "type": "boolean",
                    "description": "Run the task in background (default: false)",
                    "default": False
                }
            },
            "required": ["description", "prompt"]
        }
    },
    # Cross-session task delegation
    {
        "name": "delegate_task",
        "description": "Delegate a task to another session for execution. Can delegate to an existing session by number, or create a new session. The target session will execute the task using its own working directory and context. Use this when you need work done in another project's context or want to run tasks in parallel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_number": {
                    "type": "integer",
                    "description": "The session number (#N) to delegate to. Not required if create_new_session is true."
                },
                "task": {
                    "type": "string",
                    "description": "The task description to execute in the target session"
                },
                "create_new_session": {
                    "type": "boolean",
                    "description": "Create a new session for this task (default: false). If true, session_number is ignored.",
                    "default": False
                },
                "working_directory": {
                    "type": "string",
                    "description": "Working directory for new session. Only used when create_new_session is true. If not specified, inherits from current session."
                },
                "session_name": {
                    "type": "string",
                    "description": "Name for the new session. Only used when create_new_session is true."
                },
                "wait_for_result": {
                    "type": "boolean",
                    "description": "Whether to wait for the task to complete (default: false for async execution)",
                    "default": False
                }
            },
            "required": ["task"]
        }
    }
]


# =============================================================================
# Session State (for Todo, Plan Mode, etc.)
# =============================================================================

_session_state = {
    "todos": [],
    "plan_mode": False,
    "plan_reason": "",
    "pending_plan": None,
    "pending_question": None,
    "context_summary": None,
    "background_agents": {}
}

def get_session_state():
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
        "background_agents": {}
    }


# =============================================================================
# Tool Implementations
# =============================================================================

def read_file(path: str, encoding: str = "utf-8") -> Dict[str, Any]:
    """Read file contents"""
    try:
        # Support relative paths from working directory
        abs_path = resolve_path(path, default_to_working_dir=False)

        if not is_path_allowed(abs_path):
            return {"error": f"Access denied: {path} is outside allowed directories"}

        if not os.path.exists(abs_path):
            return {"error": f"File not found: {path}"}

        if not os.path.isfile(abs_path):
            return {"error": f"Not a file: {path}"}

        # Check file size (limit to 1MB for text files)
        size = os.path.getsize(abs_path)
        if size > 1024 * 1024:
            return {"error": f"File too large ({size} bytes). Maximum is 1MB."}

        # Try to read as text
        try:
            with open(abs_path, 'r', encoding=encoding) as f:
                content = f.read()
            return {
                "content": content,
                "path": abs_path,
                "size": size,
                "encoding": encoding
            }
        except UnicodeDecodeError:
            # Binary file - return base64
            with open(abs_path, 'rb') as f:
                content = base64.b64encode(f.read()).decode('ascii')
            return {
                "content": content,
                "path": abs_path,
                "size": size,
                "encoding": "base64",
                "is_binary": True
            }
    except Exception as e:
        return {"error": str(e)}


def write_file(path: str, content: str, encoding: str = "utf-8") -> Dict[str, Any]:
    """Write content to file"""
    try:
        # Support relative paths from working directory
        abs_path = resolve_path(path, default_to_working_dir=False)

        if not is_path_allowed_for_write(abs_path):
            return {"error": f"Access denied: {path} is outside allowed write directories"}

        # Create parent directories if needed
        parent = os.path.dirname(abs_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent)

        with open(abs_path, 'w', encoding=encoding) as f:
            f.write(content)

        return {
            "success": True,
            "path": abs_path,
            "size": len(content.encode(encoding))
        }
    except Exception as e:
        return {"error": str(e)}


def list_directory(path: str = None, show_hidden: bool = False) -> Dict[str, Any]:
    """List directory contents"""
    try:
        abs_path = resolve_path(path)

        if not is_path_allowed(abs_path):
            return {"error": f"Access denied: {path} is outside allowed directories"}

        if not os.path.exists(abs_path):
            return {"error": f"Directory not found: {path}"}

        if not os.path.isdir(abs_path):
            return {"error": f"Not a directory: {path}"}

        entries = []
        for name in os.listdir(abs_path):
            if not show_hidden and name.startswith('.'):
                continue

            entry_path = os.path.join(abs_path, name)
            entry = {
                "name": name,
                "type": "directory" if os.path.isdir(entry_path) else "file"
            }

            try:
                stat = os.stat(entry_path)
                entry["size"] = stat.st_size
                entry["modified"] = stat.st_mtime
            except:
                pass

            entries.append(entry)

        # Sort: directories first, then by name
        entries.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))

        return {
            "path": abs_path,
            "entries": entries,
            "count": len(entries)
        }
    except Exception as e:
        return {"error": str(e)}


def search_files(path: str = None, pattern: str = "*") -> Dict[str, Any]:
    """Search for files matching pattern"""
    try:
        abs_path = resolve_path(path)

        if not is_path_allowed(abs_path):
            return {"error": f"Access denied: {path} is outside allowed directories"}

        if not os.path.exists(abs_path):
            return {"error": f"Directory not found: {path}"}

        search_pattern = os.path.join(abs_path, pattern)
        matches = glob_module.glob(search_pattern, recursive=True)

        # Limit results
        if len(matches) > 100:
            matches = matches[:100]
            truncated = True
        else:
            truncated = False

        results = []
        for match in matches:
            rel_path = os.path.relpath(match, abs_path)
            results.append({
                "path": match,
                "relative_path": rel_path,
                "type": "directory" if os.path.isdir(match) else "file"
            })

        return {
            "matches": results,
            "count": len(results),
            "truncated": truncated
        }
    except Exception as e:
        return {"error": str(e)}


# Background task tracking
_background_tasks = {}
_task_counter = 0


def execute_command(command: str, working_directory: str = None, timeout: int = 60,
                   run_in_background: bool = False, description: str = None) -> Dict[str, Any]:
    """
    Execute shell command.

    Args:
        command: Shell command to execute
        working_directory: Directory to run command in
        timeout: Timeout in seconds (ignored for background tasks)
        run_in_background: If True, run command in background and return task_id
        description: Optional description for background task tracking
    """
    global _task_counter

    try:
        if not is_command_safe(command):
            return {"error": "Command blocked for safety reasons"}

        # Use provided working_directory, or fall back to global _working_dir, or cwd
        cwd = resolve_path(working_directory)
        if not is_path_allowed(cwd):
            return {"error": f"Access denied: {cwd} is outside allowed directories"}
        if not os.path.isdir(cwd):
            return {"error": f"Working directory not found: {cwd}"}

        if run_in_background:
            # Run in background using Popen
            import threading
            import time

            _task_counter += 1
            task_id = f"task_{_task_counter}"

            # Create output file for this task
            output_file = f"/tmp/claude_task_{task_id}.output"

            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=cwd
            )

            _background_tasks[task_id] = {
                "process": process,
                "command": command,
                "description": description or command[:50],
                "started_at": time.time(),
                "output_file": output_file,
                "status": "running"
            }

            # Start thread to capture output
            def capture_output():
                output = []
                try:
                    for line in process.stdout:
                        output.append(line)
                    process.wait()
                except:
                    pass
                finally:
                    # Write output to file
                    with open(output_file, 'w') as f:
                        f.write(''.join(output))
                    _background_tasks[task_id]["status"] = "completed"
                    _background_tasks[task_id]["return_code"] = process.returncode

            thread = threading.Thread(target=capture_output, daemon=True)
            thread.start()

            return {
                "success": True,
                "task_id": task_id,
                "status": "running",
                "output_file": output_file,
                "message": f"Command started in background. Use get_task_status('{task_id}') to check progress."
            }
        else:
            # Execute synchronously
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd
            )

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
                "command": command,
                "working_directory": cwd or os.getcwd()
            }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout} seconds"}
    except Exception as e:
        return {"error": str(e)}


def get_task_status(task_id: str) -> Dict[str, Any]:
    """Get the status and output of a background task"""
    if task_id not in _background_tasks:
        return {"error": f"Unknown task: {task_id}"}

    task = _background_tasks[task_id]

    result = {
        "task_id": task_id,
        "command": task["command"],
        "description": task["description"],
        "status": task["status"],
        "started_at": task["started_at"]
    }

    if task["status"] == "completed":
        result["return_code"] = task.get("return_code")
        # Read output from file
        try:
            with open(task["output_file"], 'r') as f:
                output = f.read()
            result["output"] = output[:50000] if len(output) > 50000 else output
            if len(output) > 50000:
                result["truncated"] = True
        except:
            result["output"] = "(output file not found)"
    else:
        result["output_file"] = task["output_file"]
        result["message"] = "Task still running. Check output_file for partial output."

    return result


def list_background_tasks() -> Dict[str, Any]:
    """List all background tasks"""
    tasks = []
    for task_id, task in _background_tasks.items():
        tasks.append({
            "task_id": task_id,
            "command": task["command"][:50],
            "description": task["description"],
            "status": task["status"],
            "started_at": task["started_at"]
        })

    return {
        "tasks": tasks,
        "count": len(tasks)
    }


def get_file_info(path: str) -> Dict[str, Any]:
    """Get file/directory information"""
    try:
        abs_path = os.path.abspath(os.path.expanduser(path))

        if not is_path_allowed(abs_path):
            return {"error": f"Access denied: {path} is outside allowed directories"}

        if not os.path.exists(abs_path):
            return {"error": f"Path not found: {path}"}

        stat = os.stat(abs_path)

        info = {
            "path": abs_path,
            "name": os.path.basename(abs_path),
            "type": "directory" if os.path.isdir(abs_path) else "file",
            "size": stat.st_size,
            "created": stat.st_ctime,
            "modified": stat.st_mtime,
            "accessed": stat.st_atime,
            "permissions": oct(stat.st_mode)[-3:]
        }

        if os.path.isfile(abs_path):
            mime_type, _ = mimetypes.guess_type(abs_path)
            info["mime_type"] = mime_type

        return info
    except Exception as e:
        return {"error": str(e)}


def create_directory(path: str) -> Dict[str, Any]:
    """Create directory"""
    try:
        abs_path = os.path.abspath(os.path.expanduser(path))

        if not is_path_allowed_for_write(abs_path):
            return {"error": f"Access denied: {path} is outside allowed write directories"}

        os.makedirs(abs_path, exist_ok=True)

        return {
            "success": True,
            "path": abs_path
        }
    except Exception as e:
        return {"error": str(e)}


def move_file(source: str, destination: str) -> Dict[str, Any]:
    """Move/rename file or directory"""
    try:
        src_path = os.path.abspath(os.path.expanduser(source))
        dst_path = os.path.abspath(os.path.expanduser(destination))

        if not is_path_allowed_for_write(src_path):
            return {"error": f"Access denied: {source} is outside allowed write directories"}
        if not is_path_allowed_for_write(dst_path):
            return {"error": f"Access denied: {destination} is outside allowed write directories"}

        if not os.path.exists(src_path):
            return {"error": f"Source not found: {source}"}

        import shutil
        shutil.move(src_path, dst_path)

        return {
            "success": True,
            "source": src_path,
            "destination": dst_path
        }
    except Exception as e:
        return {"error": str(e)}


def delete_file(path: str) -> Dict[str, Any]:
    """Delete file or empty directory"""
    try:
        abs_path = os.path.abspath(os.path.expanduser(path))

        if not is_path_allowed_for_write(abs_path):
            return {"error": f"Access denied: {path} is outside allowed write directories"}

        if not os.path.exists(abs_path):
            return {"error": f"Path not found: {path}"}

        if os.path.isdir(abs_path):
            os.rmdir(abs_path)  # Only removes empty directories
        else:
            os.remove(abs_path)

        return {
            "success": True,
            "path": abs_path
        }
    except OSError as e:
        if "not empty" in str(e).lower() or e.errno == 66:
            return {"error": "Directory is not empty. Use execute_command with 'rm -r' for non-empty directories."}
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# Git Tool Implementations
# =============================================================================

def _run_git_command(args: List[str], cwd: str = None) -> Dict[str, Any]:
    """Helper to run git commands"""
    try:
        # Use provided cwd, or fall back to global _working_dir
        cwd = resolve_path(cwd)
        if not is_path_allowed(cwd):
            return {"error": f"Access denied: {cwd} is outside allowed directories"}

        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=cwd
        )

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
            "success": result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        return {"error": "Git command timed out"}
    except Exception as e:
        return {"error": str(e)}


def git_status(path: str = None) -> Dict[str, Any]:
    """Get git repository status"""
    result = _run_git_command(["status", "--porcelain", "-b"], cwd=path)
    if "error" in result:
        return result

    if not result["success"]:
        return {"error": result["stderr"] or "Not a git repository"}

    lines = result["stdout"].strip().split("\n") if result["stdout"].strip() else []

    status = {
        "branch": None,
        "staged": [],
        "modified": [],
        "untracked": [],
        "deleted": []
    }

    for line in lines:
        if line.startswith("##"):
            # Branch info
            status["branch"] = line[3:].split("...")[0] if "..." in line else line[3:]
        elif line.startswith("A "):
            status["staged"].append(line[3:])
        elif line.startswith("M "):
            status["staged"].append(line[3:])
        elif line.startswith(" M"):
            status["modified"].append(line[3:])
        elif line.startswith("??"):
            status["untracked"].append(line[3:])
        elif line.startswith(" D") or line.startswith("D "):
            status["deleted"].append(line[3:])

    return status


def git_log(path: str = None, max_count: int = 10, oneline: bool = False) -> Dict[str, Any]:
    """View commit history"""
    args = ["log", f"-{max_count}"]
    if oneline:
        args.append("--oneline")
    else:
        args.extend(["--pretty=format:%H|%an|%ae|%ad|%s", "--date=iso"])

    result = _run_git_command(args, cwd=path)
    if "error" in result:
        return result

    if not result["success"]:
        return {"error": result["stderr"] or "Failed to get git log"}

    if oneline:
        return {"commits": result["stdout"].strip().split("\n") if result["stdout"].strip() else []}

    commits = []
    for line in result["stdout"].strip().split("\n"):
        if line and "|" in line:
            parts = line.split("|", 4)
            if len(parts) >= 5:
                commits.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "email": parts[2],
                    "date": parts[3],
                    "message": parts[4]
                })

    return {"commits": commits}


def git_diff(path: str = None, file: str = None, staged: bool = False) -> Dict[str, Any]:
    """Show changes"""
    args = ["diff"]
    if staged:
        args.append("--staged")
    if file:
        args.append("--")
        args.append(file)

    result = _run_git_command(args, cwd=path)
    if "error" in result:
        return result

    return {"diff": result["stdout"], "success": result["success"]}


def git_add(files: List[str], path: str = None) -> Dict[str, Any]:
    """Add files to staging area"""
    if not files:
        return {"error": "No files specified"}

    args = ["add"] + files
    result = _run_git_command(args, cwd=path)
    if "error" in result:
        return result

    if not result["success"]:
        return {"error": result["stderr"] or "Failed to add files"}

    return {"success": True, "files": files}


def git_commit(message: str, path: str = None) -> Dict[str, Any]:
    """Create a commit"""
    if not message:
        return {"error": "Commit message is required"}

    result = _run_git_command(["commit", "-m", message], cwd=path)
    if "error" in result:
        return result

    if not result["success"]:
        return {"error": result["stderr"] or "Failed to commit"}

    return {"success": True, "message": message, "output": result["stdout"]}


def git_branch(path: str = None, name: str = None, action: str = "list") -> Dict[str, Any]:
    """Manage branches"""
    if action == "list":
        result = _run_git_command(["branch", "-a"], cwd=path)
        if "error" in result:
            return result

        branches = []
        current = None
        for line in result["stdout"].strip().split("\n"):
            if line.strip():
                if line.startswith("*"):
                    current = line[2:].strip()
                    branches.append(current)
                else:
                    branches.append(line.strip())

        return {"branches": branches, "current": current}

    elif action == "create":
        if not name:
            return {"error": "Branch name is required"}
        result = _run_git_command(["branch", name], cwd=path)
        if "error" in result:
            return result
        return {"success": result["success"], "branch": name, "action": "created"}

    elif action == "delete":
        if not name:
            return {"error": "Branch name is required"}
        result = _run_git_command(["branch", "-d", name], cwd=path)
        if "error" in result:
            return result
        return {"success": result["success"], "branch": name, "action": "deleted"}

    return {"error": f"Unknown action: {action}"}


def git_checkout(target: str, path: str = None, create: bool = False) -> Dict[str, Any]:
    """Switch branches or restore files"""
    args = ["checkout"]
    if create:
        args.append("-b")
    args.append(target)

    result = _run_git_command(args, cwd=path)
    if "error" in result:
        return result

    if not result["success"]:
        return {"error": result["stderr"] or f"Failed to checkout {target}"}

    return {"success": True, "target": target, "created": create}


def git_pull(path: str = None, remote: str = "origin", branch: str = None) -> Dict[str, Any]:
    """Pull from remote"""
    args = ["pull", remote]
    if branch:
        args.append(branch)

    result = _run_git_command(args, cwd=path)
    if "error" in result:
        return result

    return {"success": result["success"], "output": result["stdout"], "errors": result["stderr"]}


def git_push(path: str = None, remote: str = "origin", branch: str = None, set_upstream: bool = False) -> Dict[str, Any]:
    """Push to remote"""
    args = ["push"]
    if set_upstream:
        args.append("-u")
    args.append(remote)
    if branch:
        args.append(branch)

    result = _run_git_command(args, cwd=path)
    if "error" in result:
        return result

    return {"success": result["success"], "output": result["stdout"], "errors": result["stderr"]}


def git_clone(url: str, path: str = None, branch: str = None) -> Dict[str, Any]:
    """Clone a repository"""
    args = ["clone"]
    if branch:
        args.extend(["-b", branch])
    args.append(url)
    if path:
        args.append(path)

    result = _run_git_command(args, cwd=os.getcwd())
    if "error" in result:
        return result

    return {"success": result["success"], "url": url, "output": result["stdout"], "errors": result["stderr"]}


# =============================================================================
# Web Search Tool Implementations
# =============================================================================

# Search engine configuration (can be updated via API)
_search_config = {
    "engine": "brave",
    "api_key": "",
    "custom_url": ""
}

def set_search_config(engine: str, api_key: str = "", custom_url: str = ""):
    """Update search engine configuration"""
    global _search_config
    _search_config["engine"] = engine
    _search_config["api_key"] = api_key
    _search_config["custom_url"] = custom_url

def get_search_config() -> Dict[str, Any]:
    """Get current search engine configuration"""
    return _search_config.copy()

def _search_brave(query: str, max_results: int, api_key: str) -> Dict[str, Any]:
    """Search using Brave Search API"""
    if not HAS_REQUESTS:
        return {"error": "Requests library not available"}
    if not api_key:
        return {"error": "Brave Search API key not configured. Set it in Settings."}
    try:
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": api_key
        }
        params = {
            "q": query,
            "count": min(max_results, 20),
            "freshness": "pw"  # pw = past week for fresh results
        }
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers=headers,
            params=params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("web", {}).get("results", []):
            results.append({
                "title": item.get("title", ""),
                "href": item.get("url", ""),
                "body": item.get("description", ""),
                "age": item.get("age", "")  # Include age info if available
            })

        return {
            "query": query,
            "engine": "brave",
            "search_time": current_time,
            "freshness": "past_week",
            "results": results,
            "count": len(results)
        }
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            return {"error": "Invalid Brave API key. Check your key in Settings."}
        return {"error": f"Brave search failed: {str(e)}"}
    except Exception as e:
        return {"error": f"Brave search failed: {str(e)}"}

def _search_tavily(query: str, max_results: int, api_key: str) -> Dict[str, Any]:
    """Search using Tavily API"""
    if not HAS_REQUESTS:
        return {"error": "Requests library not available"}
    if not api_key:
        return {"error": "Tavily API key not configured. Set it in Settings."}
    try:
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        headers = {
            "Content-Type": "application/json"
        }
        payload = {
            "api_key": api_key,
            "query": query,
            "max_results": min(max_results, 10),
            "include_answer": True,
            "days": 7  # Limit to past 7 days for fresh results
        }
        response = requests.post(
            "https://api.tavily.com/search",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "href": item.get("url", ""),
                "body": item.get("content", ""),
                "published_date": item.get("published_date", "")  # Include date if available
            })

        return {
            "query": query,
            "engine": "tavily",
            "search_time": current_time,
            "freshness": "past_7_days",
            "answer": data.get("answer", ""),
            "results": results,
            "count": len(results)
        }
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            return {"error": "Invalid Tavily API key. Check your key in Settings."}
        return {"error": f"Tavily search failed: {str(e)}"}
    except Exception as e:
        return {"error": f"Tavily search failed: {str(e)}"}

def _search_custom(query: str, max_results: int, api_key: str, custom_url: str) -> Dict[str, Any]:
    """Search using custom API"""
    if not HAS_REQUESTS:
        return {"error": "Requests library not available"}
    if not custom_url:
        return {"error": "Custom search URL not configured. Set it in Settings."}
    try:
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Replace {query} placeholder
        url = custom_url.replace("{query}", requests.utils.quote(query))

        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        # Try to parse as JSON
        try:
            data = response.json()
            # Try common response formats
            if isinstance(data, list):
                results = data[:max_results]
            elif "results" in data:
                results = data["results"][:max_results]
            elif "items" in data:
                results = data["items"][:max_results]
            else:
                results = [data]
        except:
            results = [{"content": response.text[:5000]}]

        return {
            "query": query,
            "engine": "custom",
            "search_time": current_time,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        return {"error": f"Custom search failed: {str(e)}"}

def web_search(query: str, max_results: int = 10) -> Dict[str, Any]:
    """Search the web using configured search engine (Brave, Tavily, or Custom)"""
    engine = _search_config.get("engine", "brave")
    api_key = _search_config.get("api_key", "")
    custom_url = _search_config.get("custom_url", "")

    # Check configuration
    if engine in ["brave", "tavily"] and not api_key:
        return {"error": f"{engine.capitalize()} Search API key not configured. Please set it in Settings."}
    if engine == "custom" and not custom_url:
        return {"error": "Custom search URL not configured. Please set it in Settings."}

    # Execute search with configured engine
    if engine == "brave":
        return _search_brave(query, max_results, api_key)
    elif engine == "tavily":
        return _search_tavily(query, max_results, api_key)
    elif engine == "custom":
        return _search_custom(query, max_results, api_key, custom_url)
    else:
        return {"error": f"Unknown search engine: {engine}"}


def web_fetch(url: str, selector: str = None) -> Dict[str, Any]:
    """Fetch web page content"""
    if not HAS_REQUESTS:
        return {"error": "Requests library not available. Install with: pip install requests beautifulsoup4"}

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        if selector:
            elements = soup.select(selector)
            text = "\n".join(el.get_text(strip=True) for el in elements)
        else:
            text = soup.get_text(separator="\n", strip=True)

        # Limit output size
        if len(text) > 50000:
            text = text[:50000] + "\n... (truncated)"

        return {
            "url": url,
            "title": soup.title.string if soup.title else None,
            "content": text,
            "length": len(text)
        }
    except Exception as e:
        return {"error": f"Failed to fetch URL: {str(e)}"}


# =============================================================================
# Browser Automation Tool Implementations (Playwright)
# =============================================================================

class BrowserManager:
    """Singleton browser manager for Playwright"""
    _instance = None
    _playwright = None
    _browser = None
    _page = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_page(self):
        if not HAS_PLAYWRIGHT:
            return None, "Playwright not available. Install with: pip install playwright && playwright install chromium"

        try:
            if self._playwright is None:
                self._playwright = sync_playwright().start()

            if self._browser is None:
                self._browser = self._playwright.chromium.launch(headless=True)

            if self._page is None:
                self._page = self._browser.new_page()

            return self._page, None
        except Exception as e:
            return None, str(e)

    def close(self):
        if self._page:
            self._page.close()
            self._page = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None


def browser_navigate(url: str, wait_until: str = "load") -> Dict[str, Any]:
    """Navigate browser to URL"""
    manager = BrowserManager.get_instance()
    page, error = manager.get_page()

    if error:
        return {"error": error}

    try:
        page.goto(url, wait_until=wait_until)
        return {
            "success": True,
            "url": page.url,
            "title": page.title()
        }
    except Exception as e:
        return {"error": f"Navigation failed: {str(e)}"}


def browser_screenshot(selector: str = None, full_page: bool = False) -> Dict[str, Any]:
    """Take a screenshot"""
    manager = BrowserManager.get_instance()
    page, error = manager.get_page()

    if error:
        return {"error": error}

    try:
        # Create temp file for screenshot
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            screenshot_path = f.name

        if selector:
            element = page.locator(selector)
            element.screenshot(path=screenshot_path)
        else:
            page.screenshot(path=screenshot_path, full_page=full_page)

        # Read and encode as base64
        with open(screenshot_path, "rb") as f:
            screenshot_data = base64.b64encode(f.read()).decode("ascii")

        # Clean up temp file
        os.unlink(screenshot_path)

        return {
            "success": True,
            "screenshot": screenshot_data,
            "encoding": "base64",
            "format": "png"
        }
    except Exception as e:
        return {"error": f"Screenshot failed: {str(e)}"}


def browser_click(selector: str) -> Dict[str, Any]:
    """Click an element"""
    manager = BrowserManager.get_instance()
    page, error = manager.get_page()

    if error:
        return {"error": error}

    try:
        page.click(selector)
        return {"success": True, "selector": selector}
    except Exception as e:
        return {"error": f"Click failed: {str(e)}"}


def browser_type(selector: str, text: str, clear: bool = True) -> Dict[str, Any]:
    """Type text into an input"""
    manager = BrowserManager.get_instance()
    page, error = manager.get_page()

    if error:
        return {"error": error}

    try:
        if clear:
            page.fill(selector, text)
        else:
            page.type(selector, text)
        return {"success": True, "selector": selector, "text": text}
    except Exception as e:
        return {"error": f"Type failed: {str(e)}"}


def browser_get_text(selector: str = None) -> Dict[str, Any]:
    """Get page or element text"""
    manager = BrowserManager.get_instance()
    page, error = manager.get_page()

    if error:
        return {"error": error}

    try:
        if selector:
            element = page.locator(selector)
            text = element.inner_text()
        else:
            text = page.inner_text("body")

        # Limit output
        if len(text) > 50000:
            text = text[:50000] + "\n... (truncated)"

        return {
            "success": True,
            "text": text,
            "length": len(text)
        }
    except Exception as e:
        return {"error": f"Get text failed: {str(e)}"}


def browser_evaluate(script: str) -> Dict[str, Any]:
    """Execute JavaScript"""
    manager = BrowserManager.get_instance()
    page, error = manager.get_page()

    if error:
        return {"error": error}

    try:
        result = page.evaluate(script)
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        return {"error": f"Script execution failed: {str(e)}"}


def browser_close() -> Dict[str, Any]:
    """Close the browser"""
    try:
        manager = BrowserManager.get_instance()
        manager.close()
        return {"success": True, "message": "Browser closed"}
    except Exception as e:
        return {"error": f"Failed to close browser: {str(e)}"}


# =============================================================================
# Unified Tool Handlers (Claude Code pattern: fewer tools, more parameters)
# =============================================================================

def git(action: str, path: str = None, **kwargs) -> Dict[str, Any]:
    """
    Unified Git tool - combines all git operations into one tool.

    Actions:
        - status: Get repository status
        - log: View commit history (max_count, oneline)
        - diff: Show changes (file, staged)
        - add: Stage files (files: list)
        - commit: Create commit (message)
        - branch: List/create/delete branches (name, action: list/create/delete)
        - checkout: Switch branches (target, create)
        - pull: Pull from remote (remote, branch)
        - push: Push to remote (remote, branch, set_upstream)
        - clone: Clone repository (url, branch)
    """
    action = action.lower()

    handlers = {
        "status": lambda: git_status(path=path),
        "log": lambda: git_log(
            path=path,
            max_count=kwargs.get("max_count", 10),
            oneline=kwargs.get("oneline", False)
        ),
        "diff": lambda: git_diff(
            path=path,
            file=kwargs.get("file"),
            staged=kwargs.get("staged", False)
        ),
        "add": lambda: git_add(
            path=path,
            files=kwargs.get("files", ["."])
        ),
        "commit": lambda: git_commit(
            path=path,
            message=kwargs.get("message", "")
        ),
        "branch": lambda: git_branch(
            path=path,
            name=kwargs.get("name"),
            action=kwargs.get("branch_action", "list")
        ),
        "checkout": lambda: git_checkout(
            path=path,
            target=kwargs.get("target", ""),
            create=kwargs.get("create", False)
        ),
        "pull": lambda: git_pull(
            path=path,
            remote=kwargs.get("remote", "origin"),
            branch=kwargs.get("branch")
        ),
        "push": lambda: git_push(
            path=path,
            remote=kwargs.get("remote", "origin"),
            branch=kwargs.get("branch"),
            set_upstream=kwargs.get("set_upstream", False)
        ),
        "clone": lambda: git_clone(
            url=kwargs.get("url", ""),
            path=path,
            branch=kwargs.get("branch")
        )
    }

    if action not in handlers:
        return {"error": f"Unknown git action: {action}. Valid actions: {', '.join(handlers.keys())}"}

    return handlers[action]()


def browser(action: str, **kwargs) -> Dict[str, Any]:
    """
    Unified Browser tool - combines all browser operations into one tool.

    Actions:
        - navigate: Navigate to URL (url, wait_until)
        - screenshot: Take screenshot (selector, full_page)
        - click: Click element (selector)
        - type: Type text (selector, text, clear)
        - get_text: Get page/element text (selector)
        - evaluate: Execute JavaScript (script)
        - close: Close browser
    """
    action = action.lower()

    handlers = {
        "navigate": lambda: browser_navigate(
            url=kwargs.get("url", ""),
            wait_until=kwargs.get("wait_until", "load")
        ),
        "screenshot": lambda: browser_screenshot(
            selector=kwargs.get("selector"),
            full_page=kwargs.get("full_page", False)
        ),
        "click": lambda: browser_click(
            selector=kwargs.get("selector", "")
        ),
        "type": lambda: browser_type(
            selector=kwargs.get("selector", ""),
            text=kwargs.get("text", ""),
            clear=kwargs.get("clear", True)
        ),
        "get_text": lambda: browser_get_text(
            selector=kwargs.get("selector")
        ),
        "evaluate": lambda: browser_evaluate(
            script=kwargs.get("script", "")
        ),
        "close": lambda: browser_close()
    }

    if action not in handlers:
        return {"error": f"Unknown browser action: {action}. Valid actions: {', '.join(handlers.keys())}"}

    return handlers[action]()


# =============================================================================
# Optimized Tools (Claude Code patterns)
# =============================================================================

def glob_files(pattern: str, path: str = None, limit: int = 100) -> Dict[str, Any]:
    """Fast file pattern matching using glob. Returns files sorted by modification time."""
    import glob as glob_module

    base_path = path or get_working_dir() or os.getcwd()

    # Security check
    if not is_path_allowed(base_path, for_write=False):
        return {"error": f"Access denied: {base_path}"}

    try:
        # Build full pattern
        if os.path.isabs(pattern):
            full_pattern = pattern
        else:
            full_pattern = os.path.join(base_path, pattern)

        # Get matching files
        matches = glob_module.glob(full_pattern, recursive=True)

        # Sort by modification time (newest first)
        matches_with_time = []
        for m in matches:
            try:
                mtime = os.path.getmtime(m)
                matches_with_time.append((m, mtime))
            except:
                matches_with_time.append((m, 0))

        matches_with_time.sort(key=lambda x: x[1], reverse=True)

        # Apply limit
        limited_matches = [m[0] for m in matches_with_time[:limit]]

        # Make paths relative to base_path for cleaner output
        relative_matches = []
        for m in limited_matches:
            try:
                rel = os.path.relpath(m, base_path)
                relative_matches.append(rel)
            except:
                relative_matches.append(m)

        return {
            "success": True,
            "pattern": pattern,
            "base_path": base_path,
            "files": relative_matches,
            "count": len(relative_matches),
            "total_matches": len(matches),
            "truncated": len(matches) > limit
        }
    except Exception as e:
        return {"error": f"Glob failed: {str(e)}"}


def grep_search(pattern: str, path: str = None, glob_pattern: str = None,
                output_mode: str = "files_with_matches", context_lines: int = 2,
                ignore_case: bool = False, limit: int = 50) -> Dict[str, Any]:
    """
    Search for content in files using regex.

    output_mode:
    - 'files_with_matches': Just return file paths (fast)
    - 'content': Return matching lines with context
    - 'count': Return match counts per file
    """
    import re
    import glob as glob_module

    base_path = path or get_working_dir() or os.getcwd()

    # Security check
    if not is_path_allowed(base_path, for_write=False):
        return {"error": f"Access denied: {base_path}"}

    try:
        # Compile regex
        flags = re.IGNORECASE if ignore_case else 0
        regex = re.compile(pattern, flags)

        # Get files to search
        if os.path.isfile(base_path):
            files_to_search = [base_path]
        else:
            if glob_pattern:
                full_glob = os.path.join(base_path, glob_pattern)
                files_to_search = glob_module.glob(full_glob, recursive=True)
            else:
                # Default: search all text files
                files_to_search = []
                for root, dirs, files in os.walk(base_path):
                    # Skip hidden directories
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    for f in files:
                        # Skip binary files
                        if not f.endswith(('.pyc', '.so', '.dll', '.exe', '.bin', '.zip', '.tar', '.gz', '.jpg', '.png', '.gif', '.pdf')):
                            files_to_search.append(os.path.join(root, f))

        results = []
        files_with_matches = []
        total_matches = 0

        for file_path in files_to_search:
            if len(results) >= limit and output_mode != "count":
                break

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()

                file_matches = []
                for line_num, line in enumerate(lines, 1):
                    if regex.search(line):
                        file_matches.append({
                            "line_number": line_num,
                            "content": line.rstrip()
                        })

                if file_matches:
                    rel_path = os.path.relpath(file_path, base_path)
                    files_with_matches.append(rel_path)
                    total_matches += len(file_matches)

                    if output_mode == "content":
                        # Add context lines
                        for match in file_matches[:limit]:
                            ln = match["line_number"]
                            start = max(0, ln - context_lines - 1)
                            end = min(len(lines), ln + context_lines)
                            context = []
                            for i in range(start, end):
                                prefix = ">" if i == ln - 1 else " "
                                context.append(f"{prefix}{i+1}: {lines[i].rstrip()}")

                            results.append({
                                "file": rel_path,
                                "line": ln,
                                "match": match["content"],
                                "context": "\n".join(context)
                            })

                            if len(results) >= limit:
                                break
                    elif output_mode == "count":
                        results.append({
                            "file": rel_path,
                            "count": len(file_matches)
                        })

            except Exception as e:
                # Skip files that can't be read
                continue

        if output_mode == "files_with_matches":
            return {
                "success": True,
                "pattern": pattern,
                "files": files_with_matches[:limit],
                "count": len(files_with_matches),
                "total_matches": total_matches
            }
        else:
            return {
                "success": True,
                "pattern": pattern,
                "results": results,
                "files_searched": len(files_to_search),
                "files_with_matches": len(files_with_matches),
                "total_matches": total_matches,
                "truncated": total_matches > limit
            }

    except re.error as e:
        return {"error": f"Invalid regex pattern: {str(e)}"}
    except Exception as e:
        return {"error": f"Grep failed: {str(e)}"}


def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> Dict[str, Any]:
    """
    Edit a file by replacing a specific string.
    More precise than write_file for modifications.
    The old_string must be unique in the file (unless replace_all=True).
    """
    # Build absolute path
    if not os.path.isabs(path):
        full_path = os.path.join(get_working_dir() or os.getcwd(), path)
    else:
        full_path = path

    # Security check
    if not is_path_allowed(full_path, for_write=True):
        return {"error": f"Write access denied: {full_path}"}

    if not os.path.exists(full_path):
        return {"error": f"File not found: {path}"}

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check occurrences
        occurrences = content.count(old_string)

        if occurrences == 0:
            return {
                "error": f"String not found in file",
                "old_string_preview": old_string[:100] + "..." if len(old_string) > 100 else old_string
            }

        if occurrences > 1 and not replace_all:
            return {
                "error": f"String found {occurrences} times. Use replace_all=True to replace all, or provide a more unique string.",
                "occurrences": occurrences
            }

        # Perform replacement
        if replace_all:
            new_content = content.replace(old_string, new_string)
            replaced_count = occurrences
        else:
            new_content = content.replace(old_string, new_string, 1)
            replaced_count = 1

        # Write back
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        return {
            "success": True,
            "path": path,
            "replacements": replaced_count,
            "message": f"Replaced {replaced_count} occurrence(s)"
        }

    except Exception as e:
        return {"error": f"Edit failed: {str(e)}"}


def read_files(paths: List[str], encoding: str = "utf-8") -> Dict[str, Any]:
    """
    Read multiple files at once.
    More efficient than multiple read_file calls for related files.
    """
    results = {}
    errors = {}

    for path in paths:
        # Build absolute path
        if not os.path.isabs(path):
            full_path = os.path.join(get_working_dir() or os.getcwd(), path)
        else:
            full_path = path

        # Security check
        if not is_path_allowed(full_path, for_write=False):
            errors[path] = "Access denied"
            continue

        if not os.path.exists(full_path):
            errors[path] = "File not found"
            continue

        try:
            with open(full_path, 'r', encoding=encoding, errors='replace') as f:
                content = f.read()

            # Limit content size
            if len(content) > 100000:
                content = content[:100000] + "\n... (truncated, file too large)"

            results[path] = {
                "content": content,
                "size": os.path.getsize(full_path),
                "lines": content.count('\n') + 1
            }
        except Exception as e:
            errors[path] = str(e)

    return {
        "success": len(results) > 0,
        "files": results,
        "errors": errors if errors else None,
        "read_count": len(results),
        "error_count": len(errors)
    }


# =============================================================================
# Skill Tool
# =============================================================================

def use_skill(skill_name: str, user_request: str = "") -> Dict[str, Any]:
    """
    Activate a skill and return its instructions.
    This is called when Claude decides to use a skill based on user's request.
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

        # Return the skill instructions in a format that Claude should follow
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


# =============================================================================
# P0: Todo Task Tracking System
# =============================================================================

def todo_write(todos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Create or update the task list"""
    global _session_state
    _session_state["todos"] = todos

    # Count by status
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
        "ui_update": "todo_panel"  # Signal frontend to update todo panel
    }


def todo_read() -> Dict[str, Any]:
    """Read the current task list"""
    todos = _session_state.get("todos", [])

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


# =============================================================================
# P1: User Question Mechanism
# =============================================================================

def ask_user(question: str, options: List[Dict[str, Any]], allow_custom: bool = True) -> Dict[str, Any]:
    """Ask the user a question and wait for their response"""
    global _session_state

    question_data = {
        "question": question,
        "options": options,
        "allow_custom": allow_custom,
        "awaiting_response": True
    }

    _session_state["pending_question"] = question_data

    return {
        "type": "user_question",
        "question": question,
        "options": options,
        "allow_custom": allow_custom,
        "awaiting_response": True,
        "ui_action": "show_question_dialog",  # Signal frontend to show dialog
        "message": "Waiting for user response..."
    }


# =============================================================================
# P1: Enhanced Safety Checks
# =============================================================================

# Dangerous command patterns with severity levels
DANGEROUS_PATTERNS = [
    {"pattern": r"rm\s+-rf\s+/(?!\w)", "severity": "critical", "reason": "Could delete entire filesystem"},
    {"pattern": r"rm\s+-rf\s+~", "severity": "critical", "reason": "Could delete home directory"},
    {"pattern": r"rm\s+-rf\s+\*", "severity": "high", "reason": "Could delete many files"},
    {"pattern": r">\s*/dev/sd", "severity": "critical", "reason": "Could overwrite disk"},
    {"pattern": r"mkfs\.", "severity": "critical", "reason": "Could format disk"},
    {"pattern": r"dd\s+if=.*of=/dev", "severity": "critical", "reason": "Could overwrite disk"},
    {"pattern": r"chmod\s+-R\s+777\s+/", "severity": "high", "reason": "Could compromise security"},
    {"pattern": r"curl.*\|\s*sh", "severity": "high", "reason": "Executing remote script"},
    {"pattern": r"wget.*\|\s*sh", "severity": "high", "reason": "Executing remote script"},
    {"pattern": r":\(\)\{\s*:\|:&\s*\};:", "severity": "critical", "reason": "Fork bomb"},
]

# Sensitive file patterns
SENSITIVE_FILE_PATTERNS = [
    {"pattern": r"\.env$", "reason": "Environment variables (may contain secrets)"},
    {"pattern": r"\.env\.", "reason": "Environment file (may contain secrets)"},
    {"pattern": r"credentials", "reason": "Credentials file"},
    {"pattern": r"password", "reason": "Password file"},
    {"pattern": r"secret", "reason": "Secret file"},
    {"pattern": r"private[_-]?key", "reason": "Private key file"},
    {"pattern": r"\.pem$", "reason": "Certificate/key file"},
    {"pattern": r"\.key$", "reason": "Key file"},
    {"pattern": r"\.ssh/", "reason": "SSH directory"},
    {"pattern": r"\.aws/", "reason": "AWS credentials"},
    {"pattern": r"\.gnupg/", "reason": "GPG keys"},
    {"pattern": r"id_rsa", "reason": "SSH private key"},
]

import re

def check_command_safety(command: str) -> Dict[str, Any]:
    """Enhanced safety check for commands"""
    issues = []

    for pattern_info in DANGEROUS_PATTERNS:
        if re.search(pattern_info["pattern"], command, re.IGNORECASE):
            issues.append({
                "severity": pattern_info["severity"],
                "reason": pattern_info["reason"],
                "pattern": pattern_info["pattern"]
            })

    if issues:
        critical = [i for i in issues if i["severity"] == "critical"]
        if critical:
            return {
                "safe": False,
                "blocked": True,
                "severity": "critical",
                "issues": issues,
                "message": f"Blocked: {critical[0]['reason']}"
            }
        return {
            "safe": False,
            "blocked": False,
            "severity": "high",
            "issues": issues,
            "requires_confirmation": True,
            "message": f"Warning: {issues[0]['reason']}"
        }

    return {"safe": True, "blocked": False}


def check_file_safety(path: str) -> Dict[str, Any]:
    """Check if file path might contain sensitive data"""
    path_lower = path.lower()

    for pattern_info in SENSITIVE_FILE_PATTERNS:
        if re.search(pattern_info["pattern"], path_lower):
            return {
                "safe": False,
                "reason": pattern_info["reason"],
                "requires_confirmation": True,
                "message": f"Warning: This appears to be a sensitive file ({pattern_info['reason']})"
            }

    return {"safe": True}


# =============================================================================
# P2: Plan Mode
# =============================================================================

def enter_plan_mode(reason: str) -> Dict[str, Any]:
    """Enter plan mode for careful task planning"""
    global _session_state

    _session_state["plan_mode"] = True
    _session_state["plan_reason"] = reason

    return {
        "success": True,
        "mode": "plan",
        "reason": reason,
        "message": "Entered plan mode. I will analyze and plan before making changes.",
        "ui_update": "plan_mode_indicator",
        "allowed_tools": [
            "read_file", "read_files", "glob", "grep", "list_directory",
            "search_files", "get_file_info", "web_search", "web_fetch",
            "todo_write", "todo_read"
        ],
        "restricted_tools": [
            "write_file", "edit", "delete_file", "move_file",
            "execute_command", "git_commit", "git_push"
        ]
    }


def exit_plan_mode(plan_summary: str, steps: List[str], files_to_modify: List[str] = None) -> Dict[str, Any]:
    """Exit plan mode and present plan for approval"""
    global _session_state

    plan = {
        "summary": plan_summary,
        "steps": steps,
        "files_to_modify": files_to_modify or [],
        "awaiting_approval": True
    }

    _session_state["pending_plan"] = plan
    _session_state["plan_mode"] = False

    return {
        "success": True,
        "mode": "normal",
        "plan": plan,
        "awaiting_approval": True,
        "ui_action": "show_plan_approval",
        "message": "Plan ready for your review. Please approve to proceed."
    }


def is_plan_mode() -> bool:
    """Check if currently in plan mode"""
    return _session_state.get("plan_mode", False)


def get_pending_plan() -> Optional[Dict]:
    """Get pending plan awaiting approval"""
    return _session_state.get("pending_plan")


def approve_plan() -> Dict[str, Any]:
    """Approve the pending plan"""
    global _session_state
    plan = _session_state.get("pending_plan")

    if not plan:
        return {"error": "No pending plan to approve"}

    _session_state["pending_plan"] = None
    plan["approved"] = True

    return {
        "success": True,
        "plan_approved": True,
        "plan": plan,
        "message": "Plan approved. Proceeding with implementation."
    }


# =============================================================================
# P2: Context Summarization
# =============================================================================

def summarize_context(summary: str, key_decisions: List[str] = None, pending_tasks: List[str] = None) -> Dict[str, Any]:
    """Save a context summary for long conversations"""
    global _session_state

    context_summary = {
        "summary": summary,
        "key_decisions": key_decisions or [],
        "pending_tasks": pending_tasks or [],
        "timestamp": __import__("datetime").datetime.now().isoformat()
    }

    _session_state["context_summary"] = context_summary

    return {
        "success": True,
        "context_summary": context_summary,
        "message": "Context summary saved. This will help maintain continuity in long conversations.",
        "ui_update": "context_indicator"
    }


def get_context_summary() -> Optional[Dict]:
    """Get the current context summary"""
    return _session_state.get("context_summary")


# =============================================================================
# P3: Specialized Agent Task
# =============================================================================

# Agent type configurations
AGENT_CONFIGS = {
    "explore": {
        "name": "Code Explorer",
        "description": "Specialized for exploring and understanding codebases",
        "tools": ["read_file", "read_files", "glob", "grep", "list_directory", "search_files", "get_file_info"],
        "system_prompt_addition": """You are a code exploration specialist. Your job is to:
- Find relevant files and understand code structure
- Trace code paths and dependencies
- Summarize what you find concisely
Focus on exploration, do not modify any files."""
    },
    "research": {
        "name": "Web Researcher",
        "description": "Specialized for web research and information gathering",
        "tools": ["web_search", "web_fetch", "read_file", "write_file"],
        "system_prompt_addition": """You are a research specialist. Your job is to:
- Search the web for relevant information
- Summarize findings clearly
- Save important information for later use
Focus on finding accurate, up-to-date information."""
    },
    "implement": {
        "name": "Code Implementer",
        "description": "Specialized for implementing code changes",
        "tools": ["read_file", "write_file", "edit", "glob", "grep", "execute_command", "git_status", "git_diff"],
        "system_prompt_addition": """You are a code implementation specialist. Your job is to:
- Implement requested features or fixes
- Write clean, maintainable code
- Test your changes when possible
Focus on correct, working implementations."""
    },
    "general": {
        "name": "General Agent",
        "description": "General purpose agent with access to all tools",
        "tools": None,  # All tools
        "system_prompt_addition": ""
    }
}


def task(description: str, prompt: str, agent_type: str = "general", run_in_background: bool = True) -> Dict[str, Any]:
    """
    Launch a background task in a new session.
    The task will execute asynchronously and results will be returned to the main session.
    """
    import uuid

    if agent_type not in AGENT_CONFIGS:
        return {"error": f"Unknown agent type: {agent_type}. Available: {list(AGENT_CONFIGS.keys())}"}

    config = AGENT_CONFIGS[agent_type]
    task_id = f"task_{uuid.uuid4().hex[:8]}"

    # Return a structure that triggers background task execution in a new session
    return {
        "success": True,
        "task_id": task_id,
        "type": "background_task",
        "ui_action": "launch_background_task",
        "description": description,
        "prompt": prompt,
        "agent_type": agent_type,
        "agent_name": config["name"],
        "create_new_session": True,
        "session_name": f"Task: {description[:30]}...",
        "message": f"Launching background task: {description}"
    }


def delegate_task(
    task: str,
    session_number: int = None,
    create_new_session: bool = False,
    working_directory: str = None,
    session_name: str = None,
    wait_for_result: bool = False
) -> Dict[str, Any]:
    """
    Delegate a task to another session for execution.
    This returns a special response that the frontend will handle
    to execute the task in the target session.

    Args:
        task: The task to execute
        session_number: Target session number (required if create_new_session is False)
        create_new_session: Create a new session for this task
        working_directory: Working directory for new session (inherits current if not specified)
        session_name: Name for the new session
        wait_for_result: Whether to wait for completion
    """
    import uuid

    # Validate parameters
    if not create_new_session and session_number is None:
        return {
            "success": False,
            "error": "Either session_number or create_new_session=true is required"
        }

    task_id = f"delegate_{uuid.uuid4().hex[:8]}"

    # Return a special response for the frontend to handle
    result = {
        "success": True,
        "task_id": task_id,
        "type": "delegate_task",
        "ui_action": "delegate_to_session",
        "task": task,
        "wait_for_result": wait_for_result,
        "status": "delegating",
        "create_new_session": create_new_session
    }

    if create_new_session:
        result["working_directory"] = working_directory  # None means inherit from current
        result["session_name"] = session_name or f"Delegated: {task[:30]}..."
        result["message"] = f"Creating new session for task: {task[:50]}..."
    else:
        result["session_number"] = session_number
        result["message"] = f"Delegating task to Session #{session_number}: {task[:50]}..."

    return result


# =============================================================================
# Tool Search (Lazy Loading)
# =============================================================================

def tool_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search for and optionally activate deferred tools.

    Similar to Claude Code's ToolSearch mechanism for lazy loading.
    """
    try:
        from tool_registry import get_tool_registry
        from mcp_client import get_mcp_manager

        registry = get_tool_registry()

        # Handle direct selection with activation
        if query.startswith("select:"):
            tool_name = query[7:].strip()

            # Check if already active
            if registry.is_active(tool_name):
                return {
                    "status": "already_active",
                    "tool": tool_name,
                    "message": f"Tool '{tool_name}' is already active and ready to use."
                }

            # Check if it's a deferred tool and activate it
            if registry.is_deferred(tool_name):
                # Get the full definition from MCP manager
                if "__" in tool_name:
                    server_name = tool_name.split("__")[0]
                    manager = get_mcp_manager()

                    if server_name in manager.servers:
                        server = manager.servers[server_name]
                        # Find the tool definition
                        for tool_def in server.get_tool_definitions():
                            if tool_def["name"] == tool_name:
                                registry.activate(tool_name, tool_def)
                                return {
                                    "status": "activated",
                                    "tool": tool_name,
                                    "description": tool_def.get("description", "")[:300],
                                    "message": f"Tool '{tool_name}' has been activated. You can now use it."
                                }

                return {
                    "status": "error",
                    "message": f"Could not activate tool '{tool_name}'. Server may not be running."
                }

            return {
                "status": "not_found",
                "message": f"Tool '{tool_name}' not found in registry."
            }

        # Keyword search
        results = registry.search(query, max_results)

        # Build response with deferred tools list
        deferred = registry.get_deferred_tools()

        return {
            "status": "search_results",
            "query": query,
            "results": results,
            "total_deferred": len(deferred),
            "deferred_tools": [t["name"] for t in deferred],
            "hint": "Use 'select:<tool_name>' to activate a deferred tool before using it."
        }

    except Exception as e:
        return {"error": f"Tool search failed: {str(e)}"}


# =============================================================================
# Tool Dispatcher
# =============================================================================

TOOL_HANDLERS = {
    "tool_search": tool_search,
    # File system tools
    "read_file": read_file,
    "write_file": write_file,
    "list_directory": list_directory,
    "search_files": search_files,
    "execute_command": execute_command,
    "get_file_info": get_file_info,
    "create_directory": create_directory,
    "move_file": move_file,
    "delete_file": delete_file,
    # Unified Git tool (Claude Code pattern)
    "git": git,
    # Legacy Git tools (for backward compatibility)
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
    # Web search tools
    "web_search": web_search,
    "web_fetch": web_fetch,
    # Unified Browser tool (Claude Code pattern)
    "browser": browser,
    # Legacy Browser tools (for backward compatibility)
    "browser_navigate": browser_navigate,
    "browser_screenshot": browser_screenshot,
    "browser_click": browser_click,
    "browser_type": browser_type,
    "browser_get_text": browser_get_text,
    "browser_evaluate": browser_evaluate,
    "browser_close": browser_close,
    # Skill tool
    "use_skill": use_skill,
    # Optimized tools (Claude Code patterns)
    "glob": glob_files,
    "grep": grep_search,
    "edit": edit_file,
    "read_files": read_files,
    # Background task tools
    "get_task_status": get_task_status,
    "list_background_tasks": list_background_tasks,
    # P0: Todo task tracking
    "todo_write": todo_write,
    "todo_read": todo_read,
    # P1: User question mechanism
    "ask_user": ask_user,
    # P2: Plan mode
    "enter_plan_mode": enter_plan_mode,
    "exit_plan_mode": exit_plan_mode,
    # P2: Context summarization
    "summarize_context": summarize_context,
    # P3: Specialized agent task
    "task": task,
    # P4: Cross-session task delegation
    "delegate_task": delegate_task,
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
                # Check if it's deferred
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

    This function dynamically generates the use_skill tool description
    based on available skills from the skill loader.
    """
    import copy

    # Make a deep copy to avoid modifying the original
    tools = copy.deepcopy(TOOL_DEFINITIONS)

    # Dynamically build skill list for use_skill tool
    if HAS_SKILL_LOADER:
        try:
            loader = get_skill_loader()
            # Reload skills to discover any new ones added since last call
            loader.reload()

            # Build skill list with descriptions
            skill_entries = []
            for skill in loader.skills.values():
                # Use the short description from skill metadata
                desc = skill.description or f"Skill for {skill.name} related tasks"
                skill_entries.append(f"- {skill.name}: {desc}")

            skill_list = "\n".join(skill_entries) if skill_entries else "No skills available"

            # Build the dynamic description
            dynamic_description = f"""Execute a skill to help complete specific types of tasks.
Use this tool when the user's request matches one of the available skills.

Available skills:
{skill_list}

When to use this tool:
- When the user explicitly mentions a skill name (e.g., "/pptx", "/pdf")
- When the user's request clearly matches a skill's purpose (e.g., "create a presentation" → pptx skill)
- When specialized workflows or templates would help complete the task

Call this tool with the skill_name and the user's original request.
The tool will return detailed instructions for completing the task."""

            # Find and update use_skill tool description
            for tool in tools:
                if tool["name"] == "use_skill":
                    tool["description"] = dynamic_description
                    break

        except Exception as e:
            # If skill loading fails, use a fallback description
            for tool in tools:
                if tool["name"] == "use_skill":
                    tool["description"] = f"Execute a skill (skill loading error: {e})"
                    break
    else:
        # No skill loader available
        for tool in tools:
            if tool["name"] == "use_skill":
                tool["description"] = "Execute a skill (skill loader not installed)"
                break

    # Add only ACTIVE MCP tools (lazy loading pattern)
    try:
        from tool_registry import get_tool_registry

        registry = get_tool_registry()

        # Get active tools
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
        import logging
        logging.getLogger(__name__).warning(f"Failed to load tool registry: {e}")

    return tools
