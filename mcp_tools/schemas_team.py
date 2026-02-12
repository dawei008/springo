"""
Team Communication Tool Schemas
JSON schemas for collaborative team tools (send_message, task_create, etc.)
Only injected into tool list when an agent is in team context.
"""

TEAM_TOOL_DEFINITIONS = [
    {
        "name": "send_message",
        "description": (
            "Send a message to a specific teammate or broadcast to the entire team.\n\n"
            "Message types:\n"
            "- 'message': Send a direct message to a specific recipient\n"
            "- 'broadcast': Send to all teammates (use sparingly)\n"
            "- 'shutdown_request': Request a teammate to shut down gracefully\n\n"
            "Always include a short summary (5-10 words) for UI preview."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["message", "broadcast", "shutdown_request"],
                    "description": "Message type: 'message' for DMs, 'broadcast' for all, 'shutdown_request' to shut down a teammate",
                },
                "recipient": {
                    "type": "string",
                    "description": "Agent name of the recipient (required for 'message' and 'shutdown_request')",
                },
                "content": {
                    "type": "string",
                    "description": "The message content",
                },
                "summary": {
                    "type": "string",
                    "description": "A 5-10 word summary shown as preview in the UI",
                },
            },
            "required": ["type", "content"],
        },
    },
    {
        "name": "task_create",
        "description": (
            "Create a new task on the shared team task board.\n\n"
            "Tasks help coordinate work between agents. Each task has:\n"
            "- subject: A brief actionable title (imperative form)\n"
            "- description: Detailed description of what needs to be done\n"
            "- active_form: Present continuous form shown while task is in progress (e.g., 'Running tests')\n\n"
            "New tasks start with status 'pending'. Use task_update to set owner and change status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Brief task title in imperative form (e.g., 'Fix authentication bug')",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of what needs to be done",
                },
                "active_form": {
                    "type": "string",
                    "description": "Present continuous form shown in spinner (e.g., 'Fixing authentication bug')",
                },
            },
            "required": ["subject", "description"],
        },
    },
    {
        "name": "task_update",
        "description": (
            "Update an existing task on the shared team task board.\n\n"
            "Common operations:\n"
            "- Mark task in_progress: set status='in_progress'\n"
            "- Mark task completed: set status='completed' (auto-resolves dependencies)\n"
            "- Assign task: set owner to agent name\n"
            "- Set dependencies: use add_blocked_by to specify prerequisite tasks\n\n"
            "When a task is completed, any tasks it blocks that become fully unblocked "
            "will be automatically notified."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The ID of the task to update",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "error"],
                    "description": "New task status",
                },
                "subject": {
                    "type": "string",
                    "description": "Updated task title",
                },
                "description": {
                    "type": "string",
                    "description": "Updated task description",
                },
                "active_form": {
                    "type": "string",
                    "description": "Updated present continuous form",
                },
                "owner": {
                    "type": "string",
                    "description": "Agent name to assign the task to",
                },
                "add_blocks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs that cannot start until this one completes",
                },
                "add_blocked_by": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs that must complete before this one can start",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "task_list",
        "description": (
            "List all tasks on the shared team task board.\n\n"
            "Returns a summary of each task including id, subject, status, owner, and blockedBy.\n"
            "Use this to see what tasks are available, check progress, or find unblocked work."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "task_get",
        "description": (
            "Get full details of a specific task from the shared team task board.\n\n"
            "Returns the complete task including description, dependencies, and status.\n"
            "Use this before starting work on a task to understand full requirements."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The ID of the task to retrieve",
                },
            },
            "required": ["task_id"],
        },
    },
]
