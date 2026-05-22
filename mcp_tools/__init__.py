"""
MCP Tools Package
Provides file system, terminal, git, and other cowork functionality
"""

# Config exports
from .config import (
    set_working_dir,
    get_working_dir,
    ALLOWED_READ_DIRECTORIES,
    ALLOWED_WRITE_DIRECTORIES,
    BLOCKED_COMMANDS,
)

# Session state exports
from .session import (
    get_session_state,
    reset_session_state,
    get_todos,
    set_todos,
    is_plan_mode,
    set_plan_mode,
    get_pending_question,
    set_pending_question,
    clear_pending_question,
)

# Utility exports
from .utilities import (
    resolve_path,
    is_path_allowed,
    is_path_allowed_for_read,
    is_path_allowed_for_write,
    is_command_safe,
)

# Core exports
from .core import (
    execute_tool,
    get_tool_definitions,
    TOOL_HANDLERS,
)

# Schema exports
from .schemas import TOOL_DEFINITIONS

# Handler exports (for direct access if needed)
from .handlers import (
    # File tools
    read_file, write_file, list_directory, search_files,
    get_file_info, create_directory, move_file, delete_file,
    execute_command, get_task_status, list_background_tasks,
    glob_files, grep_search, edit_file, read_files,
    kill_active_processes,
    # Git tools
    git, git_status, git_log, git_diff, git_add, git_commit,
    git_branch, git_checkout, git_pull, git_push, git_clone,
    # Browser tools removed - use MCP playwright instead
    # Search tools
    web_search, web_fetch, set_search_config, get_search_config,
    # Task tools
    todo_write, todo_read, ask_user, use_skill, tool_search,
    # Planning tools
    enter_plan_mode, exit_plan_mode, summarize_context,
    # Advanced tools
    task, delegate_task,
    # Scheduler tools
    scheduler,
    # Memory tools
    memory_search, memory_get,
    # Knowledge base tools
    kb_list, kb_search, kb_read_page, kb_write_page,
    kb_ingest_text, kb_ingest_file, kb_ingest_pdf, kb_lint, kb_stats,
    # ACP agent tools
    acp_prompt, acp_list_agents, acp_new_session,
)

__all__ = [
    # Config
    "set_working_dir", "get_working_dir",
    "ALLOWED_READ_DIRECTORIES", "ALLOWED_WRITE_DIRECTORIES", "BLOCKED_COMMANDS",
    # Session
    "get_session_state", "reset_session_state",
    "get_todos", "set_todos", "is_plan_mode", "set_plan_mode",
    "get_pending_question", "set_pending_question", "clear_pending_question",
    # Utilities
    "resolve_path", "is_path_allowed", "is_path_allowed_for_read",
    "is_path_allowed_for_write", "is_command_safe",
    # Core
    "execute_tool", "get_tool_definitions", "TOOL_HANDLERS", "TOOL_DEFINITIONS",
    # File tools
    "read_file", "write_file", "list_directory", "search_files",
    "get_file_info", "create_directory", "move_file", "delete_file",
    "execute_command", "get_task_status", "list_background_tasks",
    "glob_files", "grep_search", "edit_file", "read_files",
    # Git tools
    "git", "git_status", "git_log", "git_diff", "git_add", "git_commit",
    "git_branch", "git_checkout", "git_pull", "git_push", "git_clone",
    # Browser tools removed - use MCP playwright instead
    # Search tools
    "web_search", "web_fetch", "set_search_config", "get_search_config",
    # Task tools
    "todo_write", "todo_read", "ask_user", "use_skill", "skill_view", "manage_skill", "tool_search",
    # Planning tools
    "enter_plan_mode", "exit_plan_mode", "summarize_context",
    # Advanced tools
    "task", "delegate_task",
    # Scheduler tools
    "scheduler",
    # Memory tools
    "memory_search", "memory_get",
    # Knowledge base tools
    "kb_list", "kb_search", "kb_read_page", "kb_write_page",
    "kb_ingest_text", "kb_ingest_file", "kb_ingest_pdf", "kb_lint", "kb_stats",
    # ACP agent tools
    "acp_prompt", "acp_list_agents", "acp_new_session",
]
