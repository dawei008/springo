"""
MCP Tool Handlers
All tool implementation functions
"""

from .file_tools import (
    read_file,
    write_file,
    list_directory,
    search_files,
    get_file_info,
    create_directory,
    move_file,
    delete_file,
    execute_command,
    get_task_status,
    list_background_tasks,
    glob_files,
    grep_search,
    edit_file,
    read_files,
    kill_active_processes,
)

from .git_tools import (
    git,
    git_status,
    git_log,
    git_diff,
    git_add,
    git_commit,
    git_branch,
    git_checkout,
    git_pull,
    git_push,
    git_clone,
)

# Browser tools removed - use MCP playwright instead

from .search_tools import (
    web_search,
    web_fetch,
    set_search_config,
    get_search_config,
)

from .task_tools import (
    todo_write,
    todo_read,
    ask_user,
    use_skill,
    tool_search,
)

from .planning_tools import (
    enter_plan_mode,
    exit_plan_mode,
    summarize_context,
)

from .advanced_tools import (
    task,
    delegate_task,
)

from .scheduler_tools import (
    scheduler,
)

from .team_comm_tools import (
    send_message_async as team_send_message,
    task_create as team_task_create,
    task_update as team_task_update,
    task_list as team_task_list,
    task_get as team_task_get,
)

from .lsp_tools import (
    lsp_go_to_definition,
    lsp_find_references,
    lsp_hover,
    lsp_document_symbols,
    lsp_workspace_symbol,
    lsp_diagnostics,
)

from .memory_tools import (
    memory_search,
    memory_get,
    memory_write,
)

from .acp_tools import (
    acp_prompt,
    acp_list_agents,
    acp_new_session,
)

from .computer_tools import computer
